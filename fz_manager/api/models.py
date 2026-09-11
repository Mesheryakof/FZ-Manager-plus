class Mod:
    def __init__(self, name, file_path, size):
        self.name = name
        self.filePath = file_path
        self.size = size


class Save:
    def __init__(self, name: str, file_path: str, size: int, slot: str):
        self.name = name
        self.filePath = file_path
        self.size = size
        self.slot = slot
