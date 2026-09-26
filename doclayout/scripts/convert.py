# Modified for DocLayout; see NOTICE for a summary of changes.
"""File exports and folder conversion with bounded process concurrency."""

import math
import multiprocessing as mp
import os

import click
from tqdm import tqdm

from doclayout.config.parser import ConfigParser
from doclayout.config.printer import CustomClickPrinter
from doclayout.filenames import export_basename, export_filename
from doclayout.layout import pipeline_manifest
from doclayout.models import create_model_dict, shutdown_models
from doclayout.output import output_exists, save_output
from doclayout.services.openai import OpenAIService
from doclayout.usage import cost_message


def convert_file(fpath, destination, options, formats):
    from doclayout.exports import (
        EXPORT_FILES,
        document_exports,
        output_targets,
        save_document_exports,
    )

    models = None
    converter = None
    try:
        basename = export_basename(fpath)
        output_targets(
            destination,
            fpath,
            [
                export_filename(basename, EXPORT_FILES[kind])
                for kind in formats
                if kind in EXPORT_FILES
            ],
        )
        parser = ConfigParser(options)
        config = parser.generate_config_dict()
        models = create_model_dict()
        converter = parser.get_converter_cls()(
            artifact_dict=models,
            config=config,
            processor_list=parser.get_processors(),
        )
        document = converter.build_document(fpath)
        outputs = document_exports(document, config, formats, basename)
        save_document_exports(outputs, destination, fpath)
        click.echo(f"Saved {len(outputs)} file(s) to {destination}")
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        if converter is not None and isinstance(
            converter.extraction_service, OpenAIService
        ):
            click.echo(cost_message(converter.extraction_service.usage))
        if models is not None:
            shutdown_models(models)


def process_single_pdf(args):
    fpath, options = args
    models = None
    converter = None
    try:
        parser = ConfigParser(options)
        config = parser.generate_config_dict()
        folder = parser.get_output_folder(fpath)
        name = parser.get_base_filename(fpath)
        if options.get("skip_existing") and output_exists(
            folder, name, fingerprint=pipeline_manifest(config)["fingerprint"]
        ):
            return 0, True
        models = create_model_dict()
        converter = parser.get_converter_cls()(
            artifact_dict=models,
            config=config,
            processor_list=parser.get_processors(),
            renderer=parser.get_renderer(),
        )
        rendered = converter(fpath)
        save_output(rendered, folder, name)
        return converter.page_count, True
    except Exception as exc:
        click.echo(f"Failed {fpath}: {exc}", err=True)
        return 0, False
    finally:
        if converter is not None and isinstance(
            converter.extraction_service, OpenAIService
        ):
            click.echo(
                f"{os.path.basename(fpath)}: {cost_message(converter.extraction_service.usage)}"
            )
        if models is not None:
            shutdown_models(models)


@click.command(
    cls=CustomClickPrinter,
    help="Convert FILE OUTPUT_DIR with selectable exports, or convert a folder using --output_dir.",
)
@click.version_option(package_name="doclayout")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("destination", required=False, type=click.Path(file_okay=False))
@click.option(
    "--all",
    "all_outputs",
    is_flag=True,
    help="Write all GUI exports and a ZIP (file input only).",
)
@click.option(
    "--markdown",
    "export_markdown",
    is_flag=True,
    help="Write Markdown and its crops (default for files).",
)
@click.option(
    "--html",
    "export_html",
    is_flag=True,
    help="Write styled HTML generated from Markdown.",
)
@click.option(
    "--json", "export_json", is_flag=True, help="Write hierarchical document JSON."
)
@click.option(
    "--chunks", "export_chunks", is_flag=True, help="Write flattened block JSON."
)
@click.option(
    "--metadata", "export_metadata", is_flag=True, help="Write extraction metadata."
)
@click.option(
    "--images",
    "export_images",
    is_flag=True,
    help="Write extracted crops, when present and enabled.",
)
@click.option(
    "--annotated-pdf",
    "export_annotated_pdf",
    is_flag=True,
    help="Write a raster PDF with estimated region boxes.",
)
@click.option(
    "--annotated-images",
    "export_annotated_images",
    is_flag=True,
    help="Write annotated page PNGs.",
)
@click.option(
    "--zip",
    "export_zip",
    is_flag=True,
    help="Write a ZIP containing the complete GUI export bundle.",
)
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    help="Worker processes. Each permits up to three API requests.",
)
@click.option("--chunk_idx", type=click.IntRange(min=0), default=0)
@click.option("--num_chunks", type=click.IntRange(min=1), default=1)
@click.option("--max_files", type=click.IntRange(min=1), default=None)
@click.option("--skip_existing", is_flag=True)
@ConfigParser.common_options
@click.pass_context
def convert_cli(ctx, input_path, destination, all_outputs, **kwargs):
    from click.core import ParameterSource

    from doclayout.exports import ALL_FORMATS

    selected = {kind for kind in ALL_FORMATS if kwargs.pop(f"export_{kind}", False)}
    explicit_format = (
        ctx.get_parameter_source("output_format") == ParameterSource.COMMANDLINE
    )
    explicit_output_dir = (
        ctx.get_parameter_source("output_dir") == ParameterSource.COMMANDLINE
    )
    if (all_outputs and selected) or (explicit_format and (all_outputs or selected)):
        raise click.UsageError(
            "Use --all, individual export flags, or --output_format, not a combination of them."
        )
    if destination and explicit_output_dir:
        raise click.UsageError(
            "Specify the destination argument or --output_dir, not both."
        )
    if destination:
        kwargs["output_dir"] = destination
    if os.path.isfile(input_path):
        if not destination and not explicit_output_dir:
            raise click.UsageError(
                "File conversion requires OUTPUT_DIR or --output_dir."
            )
        for name in (
            "workers",
            "chunk_idx",
            "num_chunks",
            "max_files",
            "skip_existing",
        ):
            if ctx.get_parameter_source(name) == ParameterSource.COMMANDLINE:
                raise click.UsageError(f"--{name} is for folder conversion only.")
            kwargs.pop(name)
        formats = ALL_FORMATS if all_outputs else selected or {kwargs["output_format"]}
        convert_file(input_path, kwargs["output_dir"], kwargs, formats)
        return
    if all_outputs or selected:
        raise click.UsageError(
            "Export selection flags require a file input. For folders, use --output_format."
        )
    in_folder = input_path
    ConfigParser(kwargs).generate_config_dict()
    if kwargs["chunk_idx"] >= kwargs["num_chunks"]:
        raise click.BadParameter("chunk_idx must be smaller than num_chunks")
    files = sorted(
        os.path.join(in_folder, name)
        for name in os.listdir(in_folder)
        if os.path.isfile(os.path.join(in_folder, name))
    )
    size = math.ceil(len(files) / kwargs["num_chunks"])
    start = kwargs["chunk_idx"] * size
    files = files[start : start + size][: kwargs["max_files"]]
    tasks = [(path, kwargs) for path in files]
    if kwargs["workers"] == 1:
        results = list(tqdm(map(process_single_pdf, tasks), total=len(tasks)))
    else:
        with mp.get_context("spawn").Pool(kwargs["workers"]) as pool:
            results = list(
                tqdm(pool.imap_unordered(process_single_pdf, tasks), total=len(tasks))
            )
    click.echo(f"Converted {sum(count for count, _ in results)} pages.")
    failures = sum(not success for _, success in results)
    if failures:
        raise click.ClickException(f"{failures} document(s) failed")
