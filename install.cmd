@echo off
poetry build
for /R dist %%F in (*.whl) do pip install %%~dpnxF