# Modified for DocLayout; see NOTICE for a summary of changes.
"""Folder conversion with explicitly bounded process concurrency."""

import math
import multiprocessing as mp
import os

import click
from tqdm import tqdm

from doclayout.config.parser import ConfigParser
from doclayout.config.printer import CustomClickPrinter
from doclayout.models import create_model_dict, shutdown_models
from doclayout.output import output_exists, save_output


def process_single_pdf(args):
    fpath, options = args
    models = None
    try:
        parser = ConfigParser(options)
        config = parser.generate_config_dict()
        folder = parser.get_output_folder(fpath)
        name = parser.get_base_filename(fpath)
        if options.get("skip_existing") and output_exists(folder, name):
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
        if models is not None:
            shutdown_models(models)


@click.command(cls=CustomClickPrinter)
@click.argument("in_folder", type=click.Path(exists=True, file_okay=False))
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
def convert_cli(in_folder, **kwargs):
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
