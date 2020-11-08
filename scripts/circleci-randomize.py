#!/usr/bin/python3

# PYTHON_ARGCOMPLETE_OK

import yaml, random, re, sys, textwrap, types, git, os.path, argparse, argcomplete

configFile = ".circleci/config.yml"
configsFile = ".circleci/configs.yml"
repository = git.Repo(".")

config : dict = {}
defaults : dict = {
    'baserevision': lambda: repository.head.commit.hexsha
}

def parseOptions():
    global args

    class PickCompleter(object):
        def __init__(self):
            self.picks = None
        def __call__(self, **kwargs):
            if self.picks is not None: return self.picks
            with open(configsFile,"rb") as f:
                conf = yaml.safe_load(f)
                self.picks = conf['configs'].keys()
            return self.picks

    parser = argparse.ArgumentParser(description="Updates the Circle CI configuration (with random job choice)")
    parser.add_argument('-f', '--force', action="store_true", help="Force update (even if already updated or if working tree is clean")
    parser.add_argument('-p', '--pick', help="Configuration to select (implies --force)").completer = PickCompleter()
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

def shouldUpdateConfig() -> bool:
    if args.force or args.pick: return True
    if not repository.is_dirty(): return False
    if repository.head.commit.diff(other=None, paths=configFile): return False
    return True

def loadConfigs():
    global configsYaml
    with open(configsFile,"rb") as f:
        configsYaml = yaml.safe_load(f)

def chooseConfig():
    global config, defaults

    if args.pick is None:
        pick = configsYaml['pick']
    else:
        pick = args.pick

    configs = configsYaml['configs']
    for k,v in configsYaml['defaults'].items():
        defaults[k] = v
    configkeys = list(configs.keys())
    if pick == 'random':
        i = random.randrange(0, len(configkeys))
        configname = configkeys[i]
    else:
        configname = pick
    config = configs[configname]
    assert 'name' not in config
    print(f"Picking configuration {configname} for Circle CI")
    config['name'] = configname

def runDefaultCode(key, code):
    code = textwrap.indent(code, '  ')
    code = f"def get_default_function():\n{code}\n"
    locals = dict()
    globals = config.copy()
    globals['get'] = getKey
    exec(code, globals, locals)
    result = locals['get_default_function']()
    if result is None: sys.exit(f"Default key {key} returned no value")
    return str(result)

def getKey(key: str) -> str:
    if key in config:
        return str(config[key])
    if key in defaults:
        code = defaults[key]
        if isinstance(code, str):
            return runDefaultCode(key, code)
        if isinstance(code, types.FunctionType):
            return code()
        raise RuntimeError(f"Code for {key} has unexpected type {type(code)}")
    sys.exit(f"Unknown substitution {key} in template. Configured keys: {config.keys()}. Default keys: {defaults.keys()}")

def makeConfig():
    with open(".circleci/template.yml","rt") as f:
        template = f.read()

    def repl(m) -> str:
        return getKey(m[1])

    result = re.sub(r"@{([a-zA-Z0-9_]+)}", repl, template)

    with open(configFile, "wt") as f:
        f.write("# Autogenerated from template.yml. Changes will be lost.\n\n")
        f.write(result)

def addConfig():
    repository.index.add([configFile])

def warnAboutCommitHook():
    preCommitFile = os.path.join(repository.common_dir, "hooks/pre-commit")

    def exists():
        if not os.path.exists(preCommitFile): return False
        with open(preCommitFile, "rt") as f:
            content = f.read()
            if content.find("scripts/circleci-randomize.py") == -1: return False
        return True

    if not exists():
        print(f"*** Add scripts/circleci-randomize.py to {preCommitFile} ***")

parseOptions()
warnAboutCommitHook()
if not shouldUpdateConfig(): sys.exit()
loadConfigs()
chooseConfig()
makeConfig()
addConfig()
