# coding=utf-8
import setuptools

########################################################################################################################

plugin_identifier = "OctoPrint-PrusaConnect-Bridge"
plugin_package = "octoprint_prusaconnectbridge"
plugin_name = "PrusaConnect-Bridge"
plugin_version = "0.1.4"
plugin_description = "OctoPrint plugin bridge to Prusa Connect (unofficial)."
plugin_author = "GlitchLab.xyz"
plugin_author_email = "contact@glitchlab.xyz"
plugin_url = "https://github.com/VisualBoy/PrusaConnect-Bridge"
plugin_license = "MIT"
plugin_additional_data = []

########################################################################################################################

def package_data_dirs(source, sub_folders):
	import os
	dirs = []

	for d in sub_folders:
		folder = os.path.join(source, d)
		if not os.path.exists(folder):
			continue

		for dirname, _, files in os.walk(folder):
			dirname = os.path.relpath(dirname, source)
			for f in files:
				dirs.append(os.path.join(dirname, f))

	return dirs

def params():
	# Our metadata, as defined above
	name = plugin_name
	version = plugin_version
	description = plugin_description
	author = plugin_author
	author_email = plugin_author_email
	url = plugin_url
	license = plugin_license

	# we only have our plugin package to install
	packages = [plugin_package]

	# we might have additional data files in sub folders that need to be installed too
	package_data = {plugin_package: package_data_dirs(plugin_package, ['static', 'templates'])}
	include_package_data = True

	# If this plugin have any package data that needs to be accessible on the file system, such as templates or static assets, thien plugin will not be	zip_safe
	zip_safe = True
 
	# Rrequirements:
	install_requires = ["prusa-connect-sdk-printer==0.7.1"]

	# Hook the plugin into the "octoprint.plugin" entry point, mapping the plugin_identifier to the plugin_package.
	# That way OctoPrint will be able to find the plugin and load it.
	entry_points = {
		"octoprint.plugin": ["OctoPrint-PrusaConnect-Bridge = octoprint_prusaconnectbridge"]
	}

	return locals()

setuptools.setup(**params())
