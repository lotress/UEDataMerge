import logging
import json
from .merge import Paths, GameConfig, PortableApp, Tools

paths = Paths()
with open(paths.configPath, 'r', encoding='utf-8') as fp:
  configData = json.load(fp)
DEBUG = configData.get('debug', False)
paths.__dict__.update(configData.get('paths', {}))
app = PortableApp(paths.UAssetDataFolder, 'UAssetGUI')

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        filename=paths.logPath, filemode='w')
  from .cli import startup, merge, scan
  args = startup(paths, configData)
  game = GameConfig(**configData['games'][args.gameName.lower()])
  tools = Tools(game, paths, DEBUG)
  if args.command == 'scan':
    scan(tools)
  elif args.command == 'merge':
    merge(app, tools, args)