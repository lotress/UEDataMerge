import argparse
import sys
from merge import GameConfig, Tools, init

def parse_args():
  parser = argparse.ArgumentParser(description='UE Mod Tool')
  parser.add_argument('command', choices=['scan', 'merge'], help='Command to execute (scan or merge)')
  parser.add_argument('gameFolder', nargs='?', help='Game folder path')
  parser.add_argument('-g', '--game', metavar='gameName', help='Specify game name')
  parser.add_argument('-a', '--all', metavar='all', default=False, help='Including data tables which appeared in only ONE mod')
  return parser.parse_args()

def get_available_games(configData):
  """Get available games, returns {display_name: key} dict"""
  return {v['name']: k for k, v in configData['games'].items()}

def print_available_games(configData):
  """Print available game options"""
  available_games = get_available_games(configData)
  print("\nAvailable games:")
  for name, key in available_games.items():
    print(f"  - {name} (key: {key})")

def startup(paths, configData):
  args = parse_args()
  gameName = args.game
  gameFolder = args.gameFolder

  if gameFolder is None:
    print("Error: Missing required argument gameFolder")
    print("Usage: UEDataMerge <command> <gameFolder> -g <gameName>")
    sys.exit(1)
  if gameName is None:
    print("Error: Missing required argument gameName")
    print("Usage: UEDataMerge <command> <gameFolder> -g <gameName>")
    print_available_games(configData)
    sys.exit(1)
  if gameName.lower() not in configData['games']:
    print(f"Error: Game name '{gameName}' not found in config")
    print_available_games(configData)
    sys.exit(1)

  paths.gameFolder = gameFolder
  return args

def merge(app, tools, args):
  app.prepare()
  packages = tools.listPackages(tools.modFolder)
  assetsToPatch, count = tools.getAssetsToPatch(packages, args.all)
  assetsToPatch = tools.mixinUserMods(assetsToPatch)
  print(f'Merging {len(assetsToPatch)} data tables of {count} mod packages.')
  print('This may take servarl minutes, please wait.')
  tools.prepare(packages)
  for package in packages:
    tools.unpack(package, package)
  tools.unpackBase(assetsToPatch)
  for asset, mods in assetsToPatch.items():
    tools.mergeAsset(asset, mods)
  tools.repack()
  tools.cleanUp()
  app.cleanUp()

def scan(tools):
  packages = tools.listPackages(tools.modFolder)
  assetsToPatch, count = tools.getAssetsToPatch(packages)
  assetsToPatch = tools.mixinUserMods(assetsToPatch)
  if not len(assetsToPatch):
    print('There are no data table mods to be merged.')
    return
  print(f'There are {count} mod packages modifying {len(assetsToPatch)} data tables.')
  for asset, mods in assetsToPatch.items():
    print(f'Data table {asset} will be modified by packages below:')
    for mod in mods:
      print(f'-\t{mod if mod else 'user json file'}')

if __name__ == '__main__':
  paths, app, configData, DEBUG = init()
  args = startup(paths, configData)
  game = GameConfig(**configData['games'][args.gameName.lower()])
  tools = Tools(game, paths, DEBUG)
  if args.command == 'scan':
    scan(tools)
  elif args.command == 'merge':
    merge(app, tools, args)