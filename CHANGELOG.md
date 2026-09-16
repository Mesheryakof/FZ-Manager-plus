## v0.2.0 (2026-09-16)

### Feat

- **tui**: make the status bar server address click to join via Steam

### Refactor

- lower Python floor to 3.11

## v0.1.2 (2026-09-16)

### Feat

- **tui**: add per-item mod upload dialog and delete-all-mods action
- **tui**: apply configured theme on startup
- **tui**: replace manual path entry with interactive pickers
- rename fork to fz-manager-plus with fzmp CLI
- **tui**: show pane titles (Logs/Menu/Mods/Saves) in their borders
- **tui**: add "Sync with server" for bulk mods/saves push and pull
- **tui**: add a persistent saves pane with download/delete
- **tui**: log unhandled crashes to a file
- **tui**: add a persistent mods pane with live toggle/delete
- **tui**: focus the menu by default on startup
- **infrastructure**: add WS event-dispatch registry and decode-error fallback
- **cli**: switch fzm/fz-manager entry point to the new TUI
- **tui**: add Manage saves flow
- **tui**: add Manage mods flow
- **tui**: show live server status and wire console input to send_command
- **tui**: persist token/region/version/slot across runs
- **tui**: add PathScreen and MultiChoiceScreen components
- **infrastructure**: port mods/saves business logic to factorio_zone session
- **tui**: add Textual dashboard prototype
- **infrastructure**: add declarative API client toolkit + factorio_zone prototype

### Fix

- **mods**: discover mod archives recursively for Steam's nested layout
- **tui**: clarify sent command log label
- **tui**: close the WS connection explicitly on quit instead of abandoning it
- **tui**: stop SelectionList crashing on mod names that wrap
- **tui**: replace manual clear+add with recompose() for live list syncs
- **tui**: fix OptionDoesNotExist crash when a live pane's item count changes
- **tui**: stop lying about default-argument types in components
- **tui**: exclude the log view from the Tab focus cycle
- **terminal**: resolve fz_manager.utils module/package name collision

### Refactor

- split app into domain/application/infrastructure/tui layers
- **terminal**: use rich.text.Text styling instead of hand-rolled ANSI
- **tui**: decompose FzManagerApp into flow controllers
- rename package directory fz_manager to fz_manager_plus
- **infrastructure**: extract shared model_config into FzBaseModel
- **tui**: replace menu string literals with a MenuAction enum
- **infrastructure**: type mod entries with a ModEntry model
- **config**: persist Settings automatically on every attribute set
- **tui**: extract SelectableList as a reusable primitive
- **config**: persist the whole Settings model, not a curated field list
- **config**: fold Storage's last-used values into Settings
- **config**: fold Storage's last-used values into Settings
- **tui**: require settings explicitly, drop the internal fallback
- **tui**: extract dashboard panes into components/
- **tui**: extract modal screens into components/
- **project**: split into api/services/ui packages, migrate to httpx
