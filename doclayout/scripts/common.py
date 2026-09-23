# Modified for DocLayout; see NOTICE for a summary of changes.
import sys

import click
import streamlit as st

from doclayout.config.parser import ConfigParser
from doclayout.config.printer import CustomClickPrinter
from doclayout.models import create_model_dict


@st.cache_data()
def parse_args():
    # Use to grab common cli options
    @ConfigParser.common_options
    def options_func():
        pass

    def extract_click_params(decorated_function):
        if hasattr(decorated_function, "__click_params__"):
            return decorated_function.__click_params__
        return []

    cmd = CustomClickPrinter("DocLayout app.")
    extracted_params = extract_click_params(options_func)
    cmd.params.extend(extracted_params)
    ctx = click.Context(cmd)
    try:
        cmd_args = sys.argv[1:]
        cmd.parse_args(ctx, cmd_args)
        return ctx.params
    except click.exceptions.ClickException as e:
        return {"error": str(e)}


@st.cache_resource()
def load_models():
    return create_model_dict()
