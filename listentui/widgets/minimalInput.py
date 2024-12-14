from textual.widgets import Input


class MinimalInput(Input):
    DEFAULT_CSS = """
    MinimalInput {
        width: auto;
        height: 1;
        padding: 0;
        border: none;
        
        &:focus {
            border: none;
        }

        &>.input--cursor,&>.input--placeholder,&>.input--suggestion,&.-invalid,&.-invalid:focus {
            border: none;
        }

        &.-invalid, &.-invalid:focus {
            color: red;
        }
    }
    """
