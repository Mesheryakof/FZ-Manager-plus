from textual.widgets._toggle_button import ToggleButton

from fz_manager.tui.components.choice_screen import ChoiceScreen
from fz_manager.tui.components.confirm_screen import ConfirmScreen
from fz_manager.tui.components.log_pane import LogPane
from fz_manager.tui.components.menu_pane import MenuPane
from fz_manager.tui.components.mods_pane import ModsPane
from fz_manager.tui.components.multi_choice_screen import MultiChoiceScreen
from fz_manager.tui.components.path_screen import PathScreen
from fz_manager.tui.components.saves_pane import SavesPane
from fz_manager.tui.components.selectable_list import SelectableList
from fz_manager.tui.components.status_bar import StatusBar
from fz_manager.tui.components.token_screen import TokenScreen

# SelectionList (ModsPane, MultiChoiceScreen) hardcodes its checkbox glyph
# via ToggleButton.BUTTON_INNER, referenced directly by class (not `self`)
# in Textual's own render_line() -- there's no CSS/public way to override
# it per-widget, so this patches it process-wide. Safe here: nothing in
# this app uses Checkbox/RadioButton (ToggleButton's other subclasses).
ToggleButton.BUTTON_INNER = "✓"

__all__ = [
    "ChoiceScreen",
    "ConfirmScreen",
    "LogPane",
    "MenuPane",
    "ModsPane",
    "MultiChoiceScreen",
    "PathScreen",
    "SavesPane",
    "SelectableList",
    "StatusBar",
    "TokenScreen",
]
