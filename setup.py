from setuptools import setup, find_packages

setup(
    name='cw',
    version='0.0.1',
    description='Cell World for research',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Vyacheslav vjache@gmail.com',
    author_email='vjache@gmail.com',
    url='https://github.com/vjache/cw',
    packages=find_packages(),
    install_requires=[
        'pygame',
        'pygame_gui'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)