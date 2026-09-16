from textual.widgets._toggle_button import ToggleButton

from fz_manager_plus.tui.components.choice_screen import ChoiceScreen
from fz_manager_plus.tui.components.confirm_screen import ConfirmScreen
from fz_manager_plus.tui.components.log_pane import LogPane
from fz_manager_plus.tui.components.menu_pane import MenuPane
from fz_manager_plus.tui.components.mods_pane import ModsPane
from fz_manager_plus.tui.components.mods_upload_screen import ModsUploadScreen, UploadItem
from fz_manager_plus.tui.components.multi_choice_screen import MultiChoiceScreen
from fz_manager_plus.tui.components.saves_pane import SavesPane
from fz_manager_plus.tui.components.selectable_list import SelectableList
from fz_manager_plus.tui.components.status_bar import StatusBar
from fz_manager_plus.tui.components.token_screen import TokenScreen
from fz_manager_plus.tui.components.version_label import VersionLabel

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
    "ModsUploadScreen",
    "MultiChoiceScreen",
    "SavesPane",
    "SelectableList",
    "StatusBar",
    "TokenScreen",
    "UploadItem",
    "VersionLabel",
]
