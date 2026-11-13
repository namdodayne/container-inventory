Files merged into the base add-on to build the forwarder package `TA-container-inventory-<target>`
(see the "Package" step in .github/workflows/build.yml and docs/splunk.md):

    default/inputs.conf             scripted input, runs bin/container_inventory.path
    bin/container-inventory[.exe]   added at build time
    bin/container_inventory.path    generated at build time: absolute binary path + `--ndjson -a`
