```sh

#TODO: make adjustments for MacOS

sudo apt install -y pipx
pipx ensurepath
#must restart shell, if first time

# uninstall, if installed
if which halp >/dev/null 2>&1; then
  pipx uninstall halp
fi

# FOR DEVELOPMENT
pipx install --editable .

# FOR PRODUCTION
# pipx install git+https://github.com/ABVStudio-net/halp.git

which halp
halp --version
halp -h
```