#! usr/bin/sh

SCRIPT=$(readlink -f "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
poetry run python "$SCRIPTPATH/listentui/__main__.py" $@
