# Modified for DocLayout; see NOTICE for a summary of changes.
from typing import Optional

import click

from doclayout.config.crawler import crawler


class CustomClickPrinter(click.Command):
    def parse_args(self, ctx, args):
        from doclayout.config.validation import validate_config

        try:
            validate_config(
                {arg[2:].split("=")[0]: True for arg in args if arg.startswith("--")}
            )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
        display_help = "config" in args and "--help" in args
        if display_help:
            click.echo(
                "Here is a list of all the Builders, Processors, Converters, Providers and Renderers in DocLayout along with their attributes:"
            )

        # Keep track of shared attributes and their types
        shared_attrs = {}

        # First pass: identify shared attributes and verify compatibility
        for base_type, base_type_dict in crawler.class_config_map.items():
            for class_name, class_map in base_type_dict.items():
                for attr, (attr_type, formatted_type, default, metadata) in class_map[
                    "config"
                ].items():
                    if attr not in shared_attrs:
                        shared_attrs[attr] = {
                            "classes": [],
                            "type": attr_type,
                            # Only default-False bools render as flags. None
                            # defaults are tri-state (auto) - they need an
                            # explicit true/false value to be overridable in
                            # both directions.
                            "is_flag": attr_type in [bool, Optional[bool]]
                            and default is False,
                            "metadata": metadata,
                            "default": default,
                        }
                    shared_attrs[attr]["classes"].append(class_name)

        # These are the types of attrs that can be set from the command line
        attr_types = [
            str,
            int,
            float,
            bool,
            Optional[int],
            Optional[float],
            Optional[str],
        ]

        # Add shared attribute options first. Skip attrs the command already
        # defines explicitly (e.g. --mode in common_options) - a duplicate
        # click.Option would shadow the explicit one and warn.
        existing_opts = {opt for param in ctx.command.params for opt in param.opts}
        for attr, info in shared_attrs.items():
            if "--" + attr in existing_opts:
                continue
            if info["type"] in attr_types:
                ctx.command.params.append(
                    click.Option(
                        ["--" + attr],
                        type=info["type"],
                        help=" ".join(info["metadata"])
                        + f" (Applies to: {', '.join(info['classes'])})",
                        default=None,  # This is important, or it sets all the default keys again in config
                        is_flag=info["is_flag"],
                        flag_value=True if info["is_flag"] else None,
                    )
                )

        # Second pass: create class-specific options
        for base_type, base_type_dict in crawler.class_config_map.items():
            if display_help:
                click.echo(f"{base_type}s:")
            for class_name, class_map in base_type_dict.items():
                if display_help and class_map["config"]:
                    click.echo(
                        f"\n  {class_name}: {class_map['class_type'].__doc__ or ''}"
                    )
                    click.echo(" " * 4 + "Attributes:")
                for attr, (attr_type, formatted_type, default, metadata) in class_map[
                    "config"
                ].items():
                    class_name_attr = class_name + "_" + attr
                    if "--" + class_name_attr in existing_opts:
                        continue

                    if display_help:
                        click.echo(" " * 8 + f"{attr} ({formatted_type}):")
                        click.echo(
                            "\n".join([f"{' ' * 12}" + desc for desc in metadata])
                        )

                    if attr_type in attr_types:
                        is_flag = (
                            attr_type in [bool, Optional[bool]] and default is False
                        )

                        # Only add class-specific options
                        ctx.command.params.append(
                            click.Option(
                                ["--" + class_name_attr, class_name_attr],
                                type=attr_type,
                                help=" ".join(metadata),
                                is_flag=is_flag,
                                default=None,  # This is important, or it sets all the default keys again in config
                            )
                        )

        if display_help:
            ctx.exit()

        super().parse_args(ctx, args)
