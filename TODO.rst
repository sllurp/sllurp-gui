

TODO:
    - Clean up the code somewhat to make more readable
    - ? Add Y range spinbox

Known issues:
    - ? Issues with higher modes than zero (1,2,3), these give weird results (might be
        backend issue because different encoding: FM0 vs Miller) (phase ambiguity)
    - ? Rolling view wrecks when a new tag comes in later on (maybe fixed)

To be implemented:
    - Settings to be reworked
    - ? Log field to display llrp logger info and other stuff
    - Fix phase diff function so it won't be unstable
    - Fix pen situation so its not limited to 8 colors
    - Add import data option to revisualise past data
    - Add a nice display/formatting of most important capabilities (freq, modes, ...)
    - ? Add tags per second per tag to table
    - ? Add more columns/info per tag to table (ex.: Impinj extra fields)
    - Import "Export tag table" feature from sllurp_gui
