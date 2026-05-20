from dataclasses import dataclass
from .merge import GameConfig, Tools, init
import mobase # pyright: ignore[reportMissingModuleSource]
from PyQt6.QtCore import QCoreApplication, qInfo, qWarning # type: ignore
from PyQt6.QtGui import QIcon # type: ignore
from PyQt6.QtWidgets import QMessageBox, QComboBox, QVBoxLayout, QHBoxLayout, QDialog, QCheckBox, QPushButton, QProgressBar, QLabel # type: ignore

@dataclass
class Args:
  all: bool = False

class ProgressDialog(QDialog):
  def __init__(self, title, parent=None):
    super().__init__(parent)
    self.setWindowTitle(title)
    layout = QVBoxLayout(self)
    self.progressBar = QProgressBar()
    layout.addWidget(self.progressBar)
    self.statusLabel = QLabel()
    layout.addWidget(self.statusLabel)

  def setRange(self, minimum, maximum):
    self.progressBar.setRange(minimum, maximum)

  def setValue(self, value):
    self.progressBar.setValue(value)
    QCoreApplication.processEvents()

  def setStatus(self, text):
    self.statusLabel.setText(text)
    QCoreApplication.processEvents()

  def setTitle(self, text):
    self.setWindowTitle(text)
    QCoreApplication.processEvents()

class Plugin(mobase.IPluginTool):
  def init(self, organizer):
    self.__organizer = organizer
    self.__game = self.pluginSetting("game")
    self.__args = Args(all=self.pluginSetting("all"))
    self.__mergeBtn = QPushButton(self.tr("Merge"))
    self.__scanBtn = QPushButton(self.tr("Scan"))
    return True

  def name(self):
    return "UE Data Mod Merge"

  def displayName(self):
    return self.name()

  def author(self):
    return "github.com/lotress"

  def description(self):
    return self.tr("A tool for merging Unreal Engine game mods that modify the same data table asset.")

  def tooltip(self):
    return self.description()

  def version(self):
    return mobase.VersionInfo(1, 0, 0, 0)

  def isActive(self):
    return True

  def pluginSetting(self, name):
    return self.__organizer.pluginSetting(self.name(), name)

  def setPluginSetting(self, name, value):
    self.__organizer.setPluginSetting(self.name(), name, value)

  def settings(self):
    return [mobase.PluginSetting('game', self.tr('The game you modded.'), None), mobase.PluginSetting('all', self.tr('Include data tables that appear in only one mod.'), False)]

  def icon(self):
    return QIcon()

  def setParentWidget(self, widget):
    self.__parentWidget = widget

  def tr(self, str):
    return QCoreApplication.translate("UEDataMerge", str)

  def display(self):
    paths.gameFolder = self.__organizer.managedGame().gameDirectory().absolutePath()
    if not self.__game:
      self.__findGame()
    dialog = QDialog(self.__parentWidget)
    dialog.setWindowTitle(self.tr(self.name()))
    layout = QVBoxLayout()
    layout.addWidget(self.__choseGame())

    allCheckBox = QCheckBox(self.tr("Also merge data tables covered by only 1 mod (no conflict, merging is optional)"))
    allCheckBox.setChecked(self.__args.all)
    allCheckBox.toggled.connect(lambda checked: setattr(self.__args, 'all', checked))
    layout.addWidget(allCheckBox)

    action = [None]
    self.__scanBtn.setToolTip(self.tr("Scan active mods in priority order, and log which data tables are modified by which mods."))
    self.__scanBtn.clicked.connect(lambda: (action.__setitem__(0, 'scan'), dialog.accept()))
    self.__mergeBtn.setToolTip(self.tr("Extract data tables modified by active mods in priority order and merge them on top of the original game data to produce a new mod."))
    self.__mergeBtn.clicked.connect(lambda: (action.__setitem__(0, 'merge'), dialog.accept()))
    self.__updateGame(self.__game)
    saveBtn = QPushButton(self.tr("Save Settings & Exit"))
    saveBtn.clicked.connect(dialog.accept)

    buttonLayout = QHBoxLayout()
    buttonLayout.addWidget(self.__scanBtn)
    buttonLayout.addWidget(self.__mergeBtn)
    buttonLayout.addWidget(saveBtn)
    layout.addLayout(buttonLayout)

    dialog.setLayout(layout)
    dialog.exec()
    self.__saveSettings()
    if action[0] == 'scan':
      self.__scan()
    elif action[0] == 'merge':
      self.__merge()

  def __modFolders(self):
    modList = self.__organizer.modList()
    mods = modList.allModsByProfilePriority()
    activated_mods = [mod for mod in mods if modList.state(mod) & mobase.ModState.ACTIVE]

    # Scan mods in priority order
    for mod in activated_mods:
      yield modList.getMod(mod).absolutePath()

  def __updateGame(self, game):
    if not game: return
    v = configData['games'][game]
    self.__tools = Tools(GameConfig(**v), paths, DEBUG)
    if self.__tools.checkGame():
      self.__game = game
      self.__mergeBtn.setEnabled(True)
      self.__scanBtn.setEnabled(True)
    else:
      self.__mergeBtn.setEnabled(False)
      self.__scanBtn.setEnabled(False)
      QMessageBox.critical(self.__parentWidget, self.tr("Unrecognized game"), self.tr("This tool could not find any game files for the current game setting. Please choose the correct one or add your settings by editing config.json in this tool's folder."))

  def __findGame(self):
    games = ((k, Tools(GameConfig(**v), paths, DEBUG)) for k, v in configData['games'].items())
    self.__game, self.__tools = next(((k, tools) for k, tools in games if tools.checkGame()), (None, None))
    if self.__game is None:
      QMessageBox.critical(self.__parentWidget, self.tr("Unrecognized game"), self.tr("This tool could not find any game files after trying all known settings. You can add your settings by editing config.json in this tool's folder."))

  def __choseGame(self):
    keys = list(configData['games'])
    values = [self.tr(v['name']) for v in configData['games'].values()]
    listWidget = QComboBox()
    listWidget.addItems(values)
    listWidget.showEvent = lambda _: listWidget.setCurrentText(self.tr(configData['games'][self.__game]['name']) if self.__game else '')
    listWidget.showEvent(None)
    listWidget.setToolTip(self.tr("Select the game you modded."))

    listWidget.currentIndexChanged.connect(lambda newIndex: self.__updateGame(keys[newIndex]))
    return listWidget

  def __saveSettings(self):
    self.setPluginSetting('game', self.__game)
    self.setPluginSetting('all', self.__args.all)

  def __scan(self):
    tools = self.__tools
    packages = sum((tools.listPackages(folder) for folder in self.__modFolders()), [])
    assetsToPatch, count = tools.getAssetsToPatch(packages)
    assetsToPatch = tools.mixinUserMods(assetsToPatch)
    if not len(assetsToPatch):
      qInfo('There are no data table mods to be merged.')
      return
    qInfo(f'There are {count} mod packages modifying {len(assetsToPatch)} data tables.')
    for asset, mods in assetsToPatch.items():
      qInfo(f'Data table {asset} will be modified by packages below:')
      for mod in mods:
        qInfo(f'-\t{mod if mod else 'user json file'}')

  def __merge(self):
    tools = self.__tools
    dialog = ProgressDialog(self.tr("Merging Data Tables"), self.__parentWidget)
    dialog.setRange(0, 0)
    dialog.show()
    try:
      app.prepare()
      packages = sum((tools.listPackages(folder) for folder in self.__modFolders()), [])
      assetsToPatch, count = tools.getAssetsToPatch(packages)
      assetsToPatch = tools.mixinUserMods(assetsToPatch, self.__args.all)
      dialog.setTitle(f'Merging {len(assetsToPatch)} data tables of {count} mod packages. This may take several minutes, please wait.')
      tools.prepare(packages)
      dialog.setStatus(self.tr('Unpacking data tables...'))
      for package in packages:
        tools.unpack(package, package)
      tools.unpackBase(assetsToPatch)
      total = sum(map(len, assetsToPatch.values()))
      dialog.setRange(0, total)
      progress = 0
      for asset, mods in assetsToPatch.items():
        dialog.setStatus(f'Processing asset: {asset}')
        for package in tools.mergeAsset(asset, mods):
          progress += 1
          if package is not None:
            dialog.setStatus(f'Patching from mod: {package}')
          else:
            dialog.setStatus('Patching user json file')
          dialog.setValue(progress)
      dialog.setStatus(self.tr('Repacking data tables into new mod...'))
      tools.repack()
      qInfo(self.tr('Merge completed successfully!'))
    except Exception as e:
      qWarning(f'Error: {e}')
    finally:
      try:
        tools.cleanUp()
      except Exception:
        pass
      try:
        app.cleanUp()
      except Exception:
        pass
      dialog.close()

createPlugin = Plugin
paths, app, configData, DEBUG = init()