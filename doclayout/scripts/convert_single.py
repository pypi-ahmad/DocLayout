# Modified for DocLayout; see NOTICE for a summary of changes.
import click

from doclayout.config.parser import ConfigParser
from doclayout.config.printer import CustomClickPrinter
from doclayout.models import create_model_dict, shutdown_models
from doclayout.output import save_output
from doclayout.services.layout import LayoutError, layout_error_message
from doclayout.services.openai import OpenAIService
from doclayout.usage import cost_message


@click.command(cls=CustomClickPrinter, help="Convert a document using GPT-6 Sol.")
@click.argument("fpath", type=click.Path(exists=True, dir_okay=False))
@ConfigParser.common_options
def convert_single_cli(fpath, **kwargs):
    parser = ConfigParser(kwargs)
    config = parser.generate_config_dict()
    models = None
    converter = None
    try:
        models = create_model_dict()
        converter = parser.get_converter_cls()(
            artifact_dict=models,
            config=config,
            processor_list=parser.get_processors(),
            renderer=parser.get_renderer(),
        )
        rendered = converter(fpath)
        folder = parser.get_output_folder(fpath)
        save_output(rendered, folder, parser.get_base_filename(fpath))
        click.echo(f"Saved output to {folder}")
    except Exception as exc:
        raise click.ClickException(
            layout_error_message(exc) if isinstance(exc, LayoutError) else str(exc)
        ) from exc
    finally:
        if converter is not None and isinstance(
            converter.extraction_service, OpenAIService
        ):
            click.echo(cost_message(converter.extraction_service.usage))
        if models is not None:
            shutdown_models(models)
