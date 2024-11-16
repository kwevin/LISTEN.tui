from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Center, Grid, Middle
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label


class QuitScreen(ModalScreen):
    DEFAULT_CSS = """
    QuitScreen {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 60;
        height: 11;
        border: thick $primary 80%;
        background: $surface;
    }

    #question {
        column-span: 2;
        height: 1fr;
        width: 1fr;
        content-align: center middle;
    }
    Button {
        width: 100%;
    }   
    """
    """Screen with a dialog to quit."""

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Are you sure you want to quit?", id="question"),
            Button("Quit", variant="error", id="quit"),
            Button("Cancel", variant="primary", id="cancel"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.exit()
        else:
            self.app.pop_screen()


DATA = [
    ["Id", "Track", "Requested By", "Played At", "Artists", "Album", "Source"],
    [
        "7941",
        "青春サツバツ論",
        "",
        "04-10-2024 11:11:14",
        "3-nen E-gumi Utatan",
        "Ansatsu Kyoushitsu OP Single - Seishun Satsubatsuron",
        "Assassination Classroom",
    ],
    ["3223", "Bolero!", "", "04-10-2024 11:06:09", "Arashi", "", ""],
    ["8471", "崩壊の日", "", "04-10-2024 11:02:03", "EastNewSound", "Tragical Garnet", ""],
    ["19012", "HORiZON", "", "04-10-2024 10:58:04", "halca", "スターティングブルー", ""],
    ["28218", "Lamy*Love♡Fest☆", "", "04-10-2024 10:54:26", "雪花ラミィ", "Lamy*Love♡Fest☆", ""],
    [
        "18291",
        "前を向いて！",
        "",
        "04-10-2024 10:50:19",
        "大城あかり (CV: 木村千咲)",
        "FLY two BLUE",
        "はるかなレシーブ",
    ],
    [
        "20747",
        "Bottleship",
        "",
        "04-10-2024 10:43:15",
        "メルク (CV: 水瀬いのり)",
        "TVアニメ「メルクストーリア -無気力少年と瓶の中の少女-」 主題歌CD",
        "メルクストーリア -無気力少年と瓶の中の少女",
    ],
    ["4464", "シルビア", "", "04-10-2024 10:37:57", "Naotaro Moriyama ( 森山直太朗 )", "", ""],
    ["4157", "Kazanbai", "", "04-10-2024 10:29:09", "French Kiss", "", ""],
    ["25509", "THE GLORY DAY (So Special Ver.)", "", "04-10-2024 10:24:10", "MISIA", "So Special Christmas", ""],
    [
        "12904",
        "アムリタ (Amrita)",
        "",
        "04-10-2024 10:19:18",
        "Hagiwara Yukiho (CV: 浅倉 杏美)",
        "THE IDOLM@STER ANIM@TION MASTER 生っすかSPECIAL 05",
        "The iDOLM@STER",
    ],
    ["16782", "遠くまで", "", "04-10-2024 10:14:50", "大原櫻子", "泣きたいくらい", ""],
    [
        "8369",
        "南無阿弥JKうらめしや?！",
        "",
        "04-10-2024 10:10:12",
        "のみこ, 大瀬良あい",
        "メイド・イン・きゅんクチュアリ☆",
        "",
    ],
    ["1692", "Every Heart", "", "04-10-2024 10:04:40", "BoA", "", "Inuyasha"],
    ["14136", "宵待雨月", "", "04-10-2024 10:00:49", "結城アイラ", "decade wind [Disc 1]", "Sola"],
]


class MyApp(App[None]):
    def compose(self) -> ComposeResult:
        with Middle(), Center():
            yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(*DATA[0])
        table.add_rows(DATA[1:])
        self.push_screen(QuitScreen())


app = MyApp()
app.run()
