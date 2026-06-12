from setuptools import setup, find_packages

setup(
    name='minicode',
    version='0.2.0',
    packages=find_packages(),
    install_requires=['httpx>=0.27', 'rich>=13.0'],
    python_requires='>=3.11',
)
