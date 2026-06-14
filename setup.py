from setuptools import find_packages, setup
import os
from glob import glob

package_name = "singulation_controller"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
         [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        # Install all launch files
        (os.path.join("share", package_name, "launch"),
         glob("launch/*.py")),
        # Install all config files
        (os.path.join("share", package_name, "config"),
         glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="ChaosBuster",
    maintainer_email="you@example.com",
    description="Stepper motor controller for LEGO Sorter V2 singulation stage",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            # ros2 run singulation_controller stepper_node
            "stepper_node = singulation_controller.stepper_node:main",
        ],
    },
)
