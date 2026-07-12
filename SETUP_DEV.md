# Set up a development environment

## Debian

### Install QGIS

Install QGIS 4 as described in the QGIS Docs:

<https://qgis.org/resources/installation-guide/#debian--ubuntu>

### Solve the Wayland warning message

QGIS shows a warning when launched with Debian 13 because of the Wayland display server. To solve the issue:

```bash
cp /usr/share/applications/org.qgis.qgis.desktop .local/share/applications
nano .local/share/applications/org.qgis.qgis.desktop
```

Modify the Exec line:

```bash
Exec=env QT_QPA_PLATFORM=xcb qgis %F
```

### Create a User Profile in QGIS

Go to the menu ``Settings → User Profiles`` and add a profile named ``gisfire-dev``

### Create a python virtual environment

To avoid the development process to break QGIS 4, create a virtual environment where you can *play* without any problem 

```bash
sudo mkdir /opt/qgis-gisfire-dev
sudo chown <user>:<group> /opt/qgis-gisfire-dev/
cd /opt/qgis-gisfire-dev
python3 -m venv ./venv --system-site-packages
```

Add a launcher script

```bash
nano run-qgis-gisfire-dev.sh
```

and add:

```bash
#! /bin/bash

source /opt/qgis-gisfire-dev/venv/bin/activate
export QT_QPA_PLATFORM=xcb
exec qgis --profile gisfire-dev "$@"
```

You can add your custom launcher:

```bash
cd
cp .local/share/applications/org.qgis.qgis.desktop .local/share/applications/qgis-gisfire.desktop
nano .local/share/applications/qgis-gisfire.desktop
```

And modify the ``Exec`` line to:

```bash
Exec=/opt/qgis-gisfire-dev/run-qgis-gisfire-dev.sh
```

You can also change the name of the app 