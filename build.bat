C:\python37\python setup.py bdist_wheel
copy dist\*.whl ..\..\
rd dist /s /q
rd build /s /q
rd pydanticbuilder.egg-info /s /q
