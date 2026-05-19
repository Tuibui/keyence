from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    cfg = os.path.join(
        get_package_share_directory('keyence_glr_driver'), 'config', 'nu_ep1.yaml'
    )
    return LaunchDescription([
        Node(
            package='keyence_glr_driver',
            executable='nu_ep1_driver',
            name='keyence_glr_driver',
            parameters=[cfg],
            output='screen',
        ),
    ])
