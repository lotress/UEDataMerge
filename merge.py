import re
import json
import os
import os.path as osp
import logging
import sys
from dataclasses import dataclass, field

@dataclass
class GameConfig:
  name: str
  ID: str
  engineVersion: str
  mapName: str = 'Mappings'
  version: str = None
  repakPackOptions: list = field(default_factory=list)
  zen: bool = False

class Paths:
  def __init__(self, gameFolder=None):
    if getattr(sys, 'frozen', False):
      me = osp.dirname(osp.abspath(sys.executable))
    else:
      try:
        me = osp.dirname(osp.abspath(__file__))
      except:
        me = os.getcwd()
    self.configPath = osp.join(me, 'config.json')
    self.logPath = osp.join(me, 'output/log.txt')
    self.tempFolder = osp.join(me, 'output/temp')
    self.outputFolder = osp.join(me, 'output/mods')
    self.baseFolder = osp.join(me, 'output/base')
    self.userPatchFolder = osp.join(me, 'patches')
    self.resultFolder = osp.join(me, 'output')
    self.UAssetCLIPath = osp.join(me, 'tools/UAssetCLI/UAssetCLI.dll')
    self.retocPath = osp.join(me, 'tools/retoc.exe')
    self.repakPath = osp.join(me, 'tools/repak.exe')
    self.UAssetDataFolder = osp.join(me, 'tools/Data')
    self.gameFolder = gameFolder

RegexPathPart = re.compile(r'([^[\]]+)|\[(\d+)\]')
PrimitiveTypes = {int, str, float, bool, type(None)}
REPLACE = 0
ADDITION = 1
isDataList = lambda v: isinstance(v, list) and all(isinstance(i, dict) and i.get('Name') is not None for i in v)
selectType = lambda v: StructItem if isDataList(v.get('Value')) and any(i['Name'] == 'ID' for i in v['Value']) else DictItem
toValue = lambda v: v.toValue() if hasattr(v, 'toValue') else [i.toValue() if hasattr(i, 'toValue') else i for i in v] if isinstance(v, list) else v
joinLists = lambda lists: sum(lists, []) if lists else []
def delNone(k):
  def g(o):
    if isinstance(o, dict) and k in o and o[k] is None:
      del o[k]
      return 1
    return 0
  return g
traverse = lambda o, f: f(o) + sum(traverse(v, f) for v in o.values()) if isinstance(o, dict) else sum(traverse(i, f) for i in o) if isinstance(o, list) else 0
class DataItem:
  def __init__(self, data, path):
    self.changes = []
    self.path = path
    self.data = data
  def __getitem__(self, key):
    return self.data.get(key)
  def __setitem__(self, k, v):
    if k in self.data and hasattr(self.data[k], 'patchBy'):
      self.data[k].patchBy(v)
    else:
      changeType = REPLACE if k in self.data else ADDITION
      if changeType is not REPLACE or self.data[k] != v:
        self.changes.append((changeType, f'{self.path}.{k}', toValue(v)))
        self.data[k] = v
  def __len__(self):
    return len(self.data)
  def typeMismatch(self, k, v):
    return v is not None and self.data[k] is not None and type(v) not in PrimitiveTypes
  def patchBy(self, other):
    for k, v in other.data.items():
      if k in self.data and type(self.data[k]) != type(v) and self.typeMismatch(k, v):
        raise ValueError(f'Type mismatch for item {self.path}.{k}: {type(self.data[k])} != {type(v)}')
      else:
        self[k] = v
  def logChanges(self):
    for changeType, path, newValue in self.changes:
      logging.info(f'REPLACE {path} with {newValue}' if changeType == REPLACE else f'ADD {path} = {newValue}')
class DictItem(DataItem):
  def __init__(self, data, path):
    for k, v in data.items():
      if isinstance(v, dict):
        data[k] = DictItem(v, f'{path}.{k}')
      elif isinstance(v, list):
        if isDataList(v):
          data[k] = ListItem(v, f'{path}.{k}')
        else:
          for i, item in enumerate(v):
            if isinstance(item, dict):
              v[i] = DictItem(item, f'{path}.{k}[{i}]')
    super().__init__(data, path)
  def toValue(self):
    self.logChanges()
    return {k: toValue(v) for k, v in self.data.items()}
class ListItem(DataItem):
  def __init__(self, data, path):
    super().__init__(data, path)
    self.data = {v['Name']: selectType(v)(v, f'{path}.{v.get('Name')}') for v in data}
    structItems = [v for v in self.data.values() if isinstance(v, StructItem) and v.id is not None]
    self.idSet = set(v.id for v in structItems)
    self.idMap = {v.id: v for v in structItems}
  def __getitem__(self, key):
    return self.data.get(key)
  def setNewId(self, item):
      if item.id in self.idSet or item.id is None:
          newId = max(self.idSet, default=0) + 1
          item.setId(newId)
      else:
          newId = item.id
      self.idSet.add(newId)
      self.idMap[newId] = item
  def __setitem__(self, key, newValue):
    if key in self.data:
      if isinstance(newValue, StructItem) and newValue.id != self.data[key].id:
        newValue.setId(self.data[key].id)
      super().__setitem__(key, newValue)
    else:
      self.changes.append((ADDITION, f'{self.path}.{key}', toValue(newValue)))
      self.data[key] = newValue
      if isinstance(newValue, StructItem):
        self.setNewId(newValue)
  def toValue(self):
    self.logChanges()
    return [v.toValue() for v in self.data.values()]
  def typeMismatch(self, k, v):
    return not (isinstance(self.data[k], StructItem) and isinstance(v, DictItem))
class StructItem(DictItem):
  def __init__(self, data, path):
    super().__init__(data, path)
    self.id = None
    value = data.get('Value')
    if isinstance(value, ListItem):
      item = value['ID']
      self.id = item['Value'] if item else None
  def setId(self, newId):
    self.id = newId
    value = self['Value']
    if isinstance(value, ListItem):
        item = value['ID']
        if item:
            item['Value'] = newId
class UAsset(DictItem):
  def __init__(self, baseFolder, assetPath):
    self.baseFolder = baseFolder
    self.assetPath = assetPath
    with open(osp.join(baseFolder, assetPath), 'r') as fp:
      data = json.load(fp)
    traverse(data, delNone('PropertyTypeName'))
    super().__init__(data, '')
  def patchBy(self, other):
    if type(other) != UAsset:
      raise ValueError(f'Type mismatch: {type(self)} != {type(other)}')
    logging.info(f'Patching {self.assetPath} with {osp.join(other.baseFolder, other.assetPath)}')
    if 'Exports' in self.data and 'Exports' in other.data and len(self.data['Exports']) == len(other.data['Exports']):
      for i, v in enumerate(other.data['Exports']):
        if hasattr(self.data['Exports'][i], 'patchBy'):
          self.data['Exports'][i].patchBy(v)
      del other.data['Exports']
    if 'NameMap' in self.data and 'NameMap' in other.data:
      self.data['NameMap'] = list({**dict.fromkeys(self.data['NameMap']), **dict.fromkeys(other.data['NameMap'])})
      del other.data['NameMap']
    super().patchBy(other)
  def __repr__(self):
    return f'UAsset({self.assetPath})'
  def getValue(self, path):
    parts = joinLists(list(map(lambda t: int(t[1]) if t[1] else t[0], RegexPathPart.findall(p))) for p in path.split('.') if p)
    current = self
    for part in parts:
      if (type(part) == int and (isinstance(current, ListItem) or isinstance(current, list))) or (isinstance(current, DictItem) or isinstance(current, dict)):
        current = current[part]
      else:
        raise ValueError(f'Invalid path: {path}')
    return current.toValue() if hasattr(current, 'toValue') else current

import subprocess

class PortableApp:
  def __init__(self, local_data_path, targetPath):
    self.appdata_root = os.environ.get("LOCALAPPDATA")
    self.target_link_path = osp.join(self.appdata_root, targetPath) # 目标位置
    self.local_data_path = osp.abspath(local_data_path)     # 你想存放数据的本地位置
    self.temp_backup_path = osp.join(self.appdata_root, f"{targetPath}_Backup_Temp")
  @staticmethod
  def is_junction(path):
    """判断一个路径是否是目录联接(Junction)"""
    import ctypes
    FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
    return attrs != -1 and (attrs & FILE_ATTRIBUTE_REPARSE_POINT)
  def cleanUp(self):
    if osp.exists(self.target_link_path) and self.is_junction(self.target_link_path):
      os.rmdir(self.target_link_path) # rmdir 删除联接时不会删除本地目录里的内容
    if osp.exists(self.temp_backup_path):
      os.rename(self.temp_backup_path, self.target_link_path)
  def prepare(self):
    # 确保本地数据目录存在
    if not osp.exists(self.local_data_path):
      os.makedirs(self.local_data_path)
    # 2. 处理已经存在的 AppData 文件夹 (防止冲突)
    if osp.exists(self.target_link_path):
      # 如果它是一个真正的文件夹，不是链接，就重命名备份
      if not self.is_junction(self.target_link_path):
        if osp.exists(self.temp_backup_path):
          # 如果备份目录也存在，可能上次程序崩溃了，这里需要处理一下
          import shutil
          shutil.rmtree(self.temp_backup_path)
        os.rename(self.target_link_path, self.temp_backup_path)
      else:
        # 如果它本来就是一个旧的链接，直接删掉
        os.rmdir(self.target_link_path)
    try:
      # 3. 创建目录联接 (Junction)
      # /J 不需要管理员权限
      subprocess.run(f'mklink /J "{self.target_link_path}" "{self.local_data_path}"',
                    shell=True, check=True, capture_output=True)
    except subprocess.CalledProcessError:
      self.cleanup()
      raise

regexChunkId = re.compile(r'pakchunk(\d+).+?\.pak', re.IGNORECASE)
regexExtracted = re.compile(r'Extracted\s+(\d+)\s+\((\d+)\s+failed\)')
changeExt = lambda newExt: lambda path: osp.splitext(path)[0] + newExt
getUassetPath = changeExt('.uasset')
getJsonPath = changeExt('.json')
getWildcardPath = changeExt('.*')
getFilePath = changeExt('')
getFileName = lambda path: osp.splitext(osp.basename(path))[0]
getSubDirs = lambda t: [osp.join(t[0], d) for d in t[1]]
getSubFiles = lambda t: [osp.join(t[0], d) for d in t[2]]
listFiles = lambda ext, folder: list(filter(lambda x: x.endswith(ext), joinLists(map(getSubFiles, os.walk(folder)))))
def getChunkId(p):
  match = regexChunkId.match(p)
  return int(match.group(1)) if match else 0
class Tools:
  def __init__(self, game: GameConfig, paths: Paths, DEBUG=False):
    self.DEBUG = DEBUG
    self.game = game
    self.myName = None
    self.basePakFolder = None
    self.__dict__.update(paths.__dict__)
    self.basePakFolder = osp.join(self.gameFolder, f'{self.game.ID}/Content/Paks')
    self.modFolder = osp.join(self.basePakFolder, '~mods')
  def getMapName(self):
    return f'{self.game.mapName}_{self.game.version}' if self.game.version else self.game.mapName
  def getBasePacks(self):
    return [osp.join(self.basePakFolder, f) for f in next(os.walk(self.basePakFolder))[2] if f.endswith(self.getPackExt())]
  def checkGame(self):
    return osp.exists(self.basePakFolder) and len(self.getBasePacks())
  def cleanUp(self):
    import shutil
    if osp.exists(self.tempFolder):
      shutil.rmtree(self.tempFolder)
    if osp.exists(self.outputFolder):
      shutil.rmtree(self.outputFolder)
    if osp.exists(self.baseFolder):
      shutil.rmtree(self.baseFolder)
  def prepare(self, packages):
    self.cleanUp()
    os.makedirs(self.tempFolder)
    os.makedirs(self.outputFolder)
    os.makedirs(self.baseFolder)
    packages = list(map(lambda p: osp.splitext(p)[0], packages))
    pp = list(filter(lambda p: p.endswith('_P'), packages))
    if not len(pp):
      pp = packages
    myName = 'merged_P'
    if self.game.zen:
      latest = max(pp, default='')
      if myName <= latest:
        leading_tildes = len(latest) - len(latest.lstrip('~'))
        myName = '~' * (leading_tildes + 1) + myName
    else:
      maxChunkId = max((getChunkId(p) for p in pp), default=0)
      myName = f'pakchunk{max(888, maxChunkId + 1)}-{myName}'
    self.myName = myName
    os.makedirs(osp.join(self.outputFolder, self.myName))
  def getPackExt(self):
    return '.utoc' if self.game.zen else '.pak'
  def runAndCapture(self, cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
      logging.error(f"Error: {result.stderr}")
      raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
    return result
  def listAssetsLegacy(self, packFile):
    result = self.runAndCapture([self.repakPath, 'list', packFile])
    lines = (line for line in result.stdout.splitlines() if line.strip())
    return [osp.splitext(uassetName)[0] for uassetName in lines if uassetName.endswith('.uasset')]
  def listAssetsZen(self, packFile):
    result = self.runAndCapture([self.retocPath, 'list', '--path', '--mount-folder', self.basePakFolder, packFile])
    lines = result.stdout.splitlines()
    data = filter(lambda t: len(t) > 3, (line.split() for line in lines if line.strip()))
    return [osp.splitext(uassetName.removeprefix('../../../'))[0] for _, _, _, uassetName in data if uassetName.endswith('.uasset')]
  def listAssets(self, packFile):
    return self.listAssetsZen(packFile) if self.game.zen else self.listAssetsLegacy(packFile)
  def listPackages(self, folder):
    if not osp.exists(folder):
      return []
    return listFiles(self.getPackExt(), folder)
  def sortPackages(self, packages):
    if self.game.zen:
      pn = []
      pp = []
      for p in packages:
        (pp if getFileName(p).endswith('_P') else pn).append(p)
      return sorted(pn) + sorted(pp)
    else:
      return sorted(packages, key=getChunkId)
  def getAssetsToPatch(self, packages):
    assetMap = {}
    packages = self.sortPackages(packages)
    count = 0
    for p in packages:
      assets = self.listAssets(p)
      if len(assets):
        count += 1
      for asset in assets:
        assetMap.setdefault(asset, []).append(p)
    return assetMap, count
  def unpack(self, modPath, package):
    if osp.isfile(modPath):
      modPaths = [modPath]
    else:
      modPaths = listFiles(self.getPackExt(), modPath)
    modName = getFileName(package)
    f = self.toLegacy if self.game.zen else self.unpackLegacy
    for p in modPaths:
      f(p, modName)
  def unpackMods(self, packages):
    for package in packages:
      self.unpack(package, package)
  def unpackBase(self, assets):
    assets = list(assets)
    if self.game.zen:
      self.unpackBaseZen(assets)
    else:
      for p in self.getBasePacks():
        self.unpackLegacy(p, '', True, assets=assets)
  def unpackLegacy(self, modPath, modName, base=False, assets=None):
    allAssets = set(self.listAssetsLegacy(modPath))
    assets = [] if assets is None else ['-f'] + joinLists(['-i', p] for p in map(getWildcardPath, assets) if p in allAssets)
    output = osp.join(self.baseFolder if base else self.outputFolder, modName)
    os.makedirs(output, exist_ok=True)
    self.runAndCapture([self.repakPath, '-g', self.game.ID, 'unpack', *assets, '-o', output, modPath])
  def unpackBaseZen(self, assets):
    for asset in assets:
      result = self.runAndCapture([self.retocPath, 'to-legacy', '--no-shaders', '--no-compres-shaders', '--no-ver-check', '--version', f'UE{self.game.engineVersion}', '-f', asset, self.basePakFolder, self.baseFolder])
      line = result.stdout.splitlines()[-1]
      match = regexExtracted.match(line)
      if match and sum(map(int, match.groups())) == 0:
        logging.warning(f'Asset {asset} not found in base packages')
  def toLegacy(self, modPath, modName, base=False):
    output = self.baseFolder if base else self.outputFolder
    outputPath = osp.join(output, modName)
    os.makedirs(outputPath, exist_ok=True)
    inputDir, fileName = osp.dirname(modPath), getFileName(modPath)
    self.runAndCapture([self.retocPath, 'to-legacy', '--no-shaders', '--no-compres-shaders', '--no-ver-check', '--version', f'UE{self.game.engineVersion}', '-f', '.uasset', '--mount-folder', self.basePakFolder, '--file-filter', fileName, inputDir, outputPath])
  def tojson(self, modName, asset):
    uassetPath = osp.join(self.outputFolder, modName, getUassetPath(asset)) if modName else osp.join(self.baseFolder, getUassetPath(asset))
    jsonPath = osp.join(self.tempFolder, getJsonPath(asset))
    os.makedirs(osp.dirname(jsonPath), exist_ok=True)
    self.runAndCapture(['dotnet', self.UAssetCLIPath, 'tojson', uassetPath, jsonPath, f'VER_UE{self.game.engineVersion}', self.getMapName()])
  def fromjson(self, asset):
    jsonPath = osp.join(self.tempFolder, getJsonPath(asset))
    uassetPath = osp.join(self.outputFolder, self.myName, getUassetPath(asset))
    os.makedirs(osp.dirname(uassetPath), exist_ok=True)
    self.runAndCapture(['dotnet', self.UAssetCLIPath, 'fromjson', jsonPath, uassetPath, self.getMapName()])
  def toZen(self):
    self.runAndCapture([self.retocPath, 'to-zen', '--version', f'UE{self.game.engineVersion}', osp.join(self.outputFolder, self.myName), osp.join(self.resultFolder, f'{self.myName}.utoc')])
  def repackLegacy(self):
    self.runAndCapture([self.repakPath, '-g', self.game.ID, 'pack', *self.game.repakPackOptions, osp.join(self.outputFolder, self.myName), osp.join(self.resultFolder, f'{self.myName}.pak')])
  def repack(self):
    self.toZen() if self.game.zen else self.repackLegacy()
  def mixinMods(self, assetsToPatch, package, modAssets, all=True):
    for mod in modAssets:
      if mod in assetsToPatch:
        assetsToPatch[mod].append(package)
      else:
        assetsToPatch[mod] = [package]
    if not all:
      for k in list(assetsToPatch):
        if len(assetsToPatch[k]) == 1:
          del assetsToPatch[k]
    return assetsToPatch
  def mixinUserMods(self, assetsToPatch, all=True):
    userMods = [getFilePath(osp.relpath(p, self.userPatchFolder).replace('\\', '/')) for p in listFiles('.json', self.userPatchFolder)]
    return self.mixinMods(assetsToPatch, None, userMods, all)
  def mergeAsset(self, asset, mods):
    print(f'\n--- Processing asset: {asset} ---')
    jsonPath = getJsonPath(asset)
    self.tojson(None, asset)
    base = UAsset(self.tempFolder, jsonPath)
    for package in mods:
      folder = self.userPatchFolder
      yield package
      if package is not None:
        print(f'Patching from mod: {package}')
        modName = getFileName(package)
        self.tojson(modName, asset)
        folder = self.tempFolder
      else:
        print('Patching ' + osp.join(self.userPatchFolder, jsonPath))
      mod = UAsset(folder, jsonPath)
      base.patchBy(mod)
    dumpOpt = dict(indent=2) if self.DEBUG else dict(separators=(',', ':'))
    with open(osp.join(self.tempFolder, jsonPath), 'w') as fp:
      json.dump(base.toValue(), fp, **dumpOpt, ensure_ascii=False)
    self.fromjson(asset)

def init():
  paths = Paths()
  with open(paths.configPath, 'r', encoding='utf-8') as fp:
    configData = json.load(fp)
  DEBUG = configData.get('debug', False)
  for k, v in configData.get('paths', {}).items():
    paths.__dict__[k] = osp.abspath(v)
  logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                      filename=paths.logPath, filemode='w')
  app = PortableApp(paths.UAssetDataFolder, 'UAssetGUI')
  return paths, app, configData, DEBUG