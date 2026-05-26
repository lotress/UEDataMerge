from dataclasses import dataclass

from .merge import GameConfig, Tools, init, deduplicate
import mobase # pyright: ignore[reportMissingModuleSource]
from PyQt6.QtCore import QCoreApplication, qInfo, qWarning # type: ignore
from PyQt6.QtGui import QIcon # type: ignore
from PyQt6.QtWidgets import QMessageBox, QComboBox, QVBoxLayout, QHBoxLayout, QDialog, QCheckBox, QPushButton, QProgressBar, QLabel, QRadioButton, QLineEdit, QDialogButtonBox # type: ignore

@dataclass
class Args:
  all: bool = False

class ProgressDialog(QDialog):
  def __init__(self, title, parent=None):
    super().__init__(parent)
    self.setWindowTitle(title)
    layout = QVBoxLayout(self)
    layout.addWidget(QLabel(self.tr("This may take several minutes, please wait.")))
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

class ResultDialog(QDialog):
  """合并完成后的结果对话框：让用户选择安装方式并输入Mod名称"""

  def __init__(self, defaultName, parent=None):
    super().__init__(parent)
    self.setWindowTitle(self.tr("Merge Completed"))
    layout = QVBoxLayout(self)

    nameLabel = QLabel(self.tr("Mod name:"))
    self.nameEdit = QLineEdit(defaultName)
    layout.addWidget(nameLabel)
    layout.addWidget(self.nameEdit)

    self.installRadio = QRadioButton(self.tr("Install as a new mod in Mod Organizer"))
    self.installRadio.setChecked(True)
    self.keepRadio = QRadioButton(self.tr("Keep files in output directory"))
    layout.addWidget(self.installRadio)
    layout.addWidget(self.keepRadio)

    buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttonBox.accepted.connect(self.accept)
    buttonBox.rejected.connect(self.reject)
    layout.addWidget(buttonBox)

  def tr(self, str):
    return QCoreApplication.translate("UEDataMerge", str)

  def shouldInstall(self):
    return self.installRadio.isChecked()

  def modName(self):
    return self.nameEdit.text()

class MergeDialog(QDialog):
  """主对话框：游戏选择、扫描/合并操作入口"""

  def __init__(self, game, args, parent=None):
    super().__init__(parent)
    self.game = game
    self.args = args
    self.tools = None
    self.action = None
    if not self.game:
      self.findGame()
    self.buildUI()

  def tr(self, str):
    return QCoreApplication.translate("UEDataMerge", str)

  def findGame(self):
    games = ((k, Tools(GameConfig(**v), paths, DEBUG)) for k, v in configData['games'].items())
    self.game, self.tools = next(((k, tools) for k, tools in games if tools.checkGame()), (None, None))
    if self.game is None:
      QMessageBox.critical(self, self.tr("Unrecognized game"), self.tr("This tool could not find any game files after trying all known settings. You can add your settings by editing config.json in this tool's folder."))

  def buildUI(self):
    self.setWindowTitle(self.tr("UE Data Mod Merge"))
    layout = QVBoxLayout()

    layout.addWidget(self.choseGame())

    allCheckBox = QCheckBox(self.tr("Also merge data tables covered by only 1 mod (no conflict, merging is optional)"))
    allCheckBox.setChecked(self.args.all)
    allCheckBox.toggled.connect(lambda checked: setattr(self.args, 'all', checked))
    layout.addWidget(allCheckBox)

    self.scanBtn = QPushButton(self.tr("Scan"))
    self.mergeBtn = QPushButton(self.tr("Merge"))
    saveBtn = QPushButton(self.tr("Save Settings & Exit"))

    self.scanBtn.setToolTip(self.tr("Scan active mods in priority order, and log which data tables are modified by which mods."))
    self.scanBtn.clicked.connect(self.onScan)
    self.mergeBtn.setToolTip(self.tr("Extract data tables modified by active mods in priority order and merge them on top of the original game data to produce a new mod."))
    self.mergeBtn.clicked.connect(self.onMerge)
    saveBtn.clicked.connect(self.accept)

    buttonLayout = QHBoxLayout()
    buttonLayout.addWidget(self.scanBtn)
    buttonLayout.addWidget(self.mergeBtn)
    buttonLayout.addWidget(saveBtn)
    layout.addLayout(buttonLayout)

    self.setLayout(layout)
    self.updateGame(self.game)

  def onScan(self):
    self.action = 'scan'
    self.accept()

  def onMerge(self):
    self.action = 'merge'
    self.accept()

  def choseGame(self):
    keys = list(configData['games'])
    values = [self.tr(v['name']) for v in configData['games'].values()]
    listWidget = QComboBox()
    listWidget.addItems(values)
    listWidget.showEvent = lambda _: listWidget.setCurrentText(self.tr(configData['games'][self.game]['name']) if self.game else '')
    listWidget.showEvent(None)
    listWidget.setToolTip(self.tr("Select the game you modded."))
    listWidget.currentIndexChanged.connect(lambda newIndex: self.updateGame(keys[newIndex]))
    return listWidget

  def updateGame(self, game):
    if not game: return
    v = configData['games'][game]
    self.tools = Tools(GameConfig(**v), paths, DEBUG)
    if self.tools.checkGame():
      self.game = game
      self.mergeBtn.setEnabled(True)
      self.scanBtn.setEnabled(True)
    else:
      self.mergeBtn.setEnabled(False)
      self.scanBtn.setEnabled(False)
      QMessageBox.critical(self, self.tr("Unrecognized game"), self.tr("This tool could not find any game files for the current game setting. Please choose the correct one or add your settings by editing config.json in this tool's folder."))

class Plugin(mobase.IPluginTool):
  def init(self, organizer):
    self.__organizer = organizer
    self.__game = self.pluginSetting("game")
    self.__args = Args(all=self.pluginSetting("all"))
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
    return [mobase.PluginSetting('game', self.tr('The game you modded.'), ''), mobase.PluginSetting('all', self.tr('Include data tables that appear in only one mod.'), False)]

  def icon(self):
    return QIcon()

  def setParentWidget(self, widget):
    self.__parentWidget = widget

  def tr(self, str):
    return QCoreApplication.translate("UEDataMerge", str)

  def display(self):
    paths.gameFolder = self.__organizer.managedGame().gameDirectory().absolutePath()
    dialog = MergeDialog(self.__game, self.__args, self.__parentWidget)
    dialog.exec()
    self.__game = dialog.game
    self.__tools = dialog.tools
    self.__args = dialog.args
    self.__saveSettings()
    if dialog.action == 'scan':
      self.__scan()
    elif dialog.action == 'merge':
      self.__merge()

  def __modFolders(self):
    modList = self.__organizer.modList()
    mods = modList.allModsByProfilePriority()
    activated_mods = [mod for mod in mods if modList.state(mod) & mobase.ModState.ACTIVE]

    # Scan mods in priority order
    for mod in activated_mods:
      yield modList.getMod(mod).absolutePath()

  def __getPackages(self):
    return deduplicate(sum((self.__tools.listPackages(folder) for folder in self.__modFolders()), []))

  def __saveSettings(self):
    self.setPluginSetting('game', self.__game)
    self.setPluginSetting('all', self.__args.all)

  def __scan(self):
    tools = self.__tools
    packages = self.__getPackages()
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
      packages = self.__getPackages()
      assetsToPatch, count = tools.getAssetsToPatch(packages)
      assetsToPatch = tools.mixinUserMods(assetsToPatch, self.__args.all)
      packages = tools.filterPackages(packages, assetsToPatch)
      dialog.setTitle(f'Merging {len(assetsToPatch)} data tables of {count} mod packages.')
      dialog.setRange(0, total)
      progress = 0
      dialog.setValue(progress)
      tools.prepare(packages)
      dialog.setStatus(self.tr('Unpacking data tables...'))
      for package in packages:
        tools.unpack(package, package)
      tools.unpackBase(assetsToPatch)
      total = sum(map(len, assetsToPatch.values()))
      for asset, mods in assetsToPatch.items():
        dialog.setStatus(f'Processing asset: {asset}')
        for package in tools.mergeAsset(asset, mods):
          progress += 1
          if package is not None:
            dialog.setStatus(f'Patching from mod: {package}')
          else:
            dialog.setStatus(f'Patching user json file {asset}')
          dialog.setValue(progress)
      dialog.setStatus(self.tr('Repacking data tables into new mod...'))
      tools.repack()
      resultDialog = ResultDialog(tools.myName, self.__parentWidget)
      if resultDialog.exec() == QDialog.DialogCode.Accepted and resultDialog.shouldInstall():
        self.__createMod(resultDialog.modName())
      qInfo(self.tr('Merge completed successfully!'))
    except Exception as e:
      qWarning(str(e))
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

  def __createMod(self, name):
    newMod = self.__organizer.createMod(name)
    if not newMod:
      return # User canceled
    version = self.__tools.moveResult(newMod.absolutePath()).split('-')[0]
    newMod.addCategory('Gameplay')
    newMod.setVersion(mobase.VersionInfo(version))
    self.__organizer.modList().setActive(newMod.name(), True)
    self.__organizer.refresh(True)

createPlugin = Plugin
paths, app, configData, DEBUG = init()