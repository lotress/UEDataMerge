@echo off
md UEDataMerge
copy *.py "UEDataMerge\"
copy config.json "UEDataMerge\"
copy .gitignore "UEDataMerge\"
copy build.bat "UEDataMerge\"
xcopy tools "UEDataMerge\tools\" /E /I /H /Y
md "UEDataMerge\output"
md "UEDataMerge\patches"

c:\soft\7-Zip\7z.exe a plugin-all-in-one.zip UEDataMerge "-x!UEDataMerge/tools/oo2core_9_win64.dll"

rd /s /q UEDataMerge
