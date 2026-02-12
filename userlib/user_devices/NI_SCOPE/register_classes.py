#####################################################################
#                                                                   #
# /NI_SCOPE/register_classes.py                                     #
#                                                                   #
# A driver for interfacing NI-SCOPE devices in labscripts           #
#                                                                   #
# Last Revised Dec. 2024, Phelan Yu                                 #
#                                                                   #
#####################################################################

import labscript_devices

labscript_devices.register_classes(
    'NI_SCOPE',
    BLACS_tab='user_devices.NI_SCOPE.blacs_tabs.NI_SCOPETab',
    runviewer_parser=None
)
