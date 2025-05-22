from typing import Literal, Any, Dict
from plugins_func.register import register_function, ToolType, ActionResponse, Action
import paho.mqtt.client as mqtt
from config.logger import setup_logging
import uuid

# 日志配置
TAG = __name__
logger = setup_logging()

# 动作类型定义
RobotAction = Literal[
    'forward', 'turn_L', 'home', 'turn_R', 'backward',
    'hello', 'omni_walk', 'moonwalk_L', 'dance', 'up_down',
    'push_up', 'front_back', 'wave_hand', 'scared'
]
ROBOT_ACTIONS = set(RobotAction.__args__)

class RobotController:
    _instance = None
    _lock = None  # 不再需要asyncio.Lock
    _connected_controller = None  # 存储已连接的控制器实例

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = object.__new__(cls)
        return cls._instance

    """MQTT机器人控制核心类（同步实现）"""
    def __init__(self,
                 client_id: str = "robot_client",
                 mqtt_host: str = "127.0.0.1",
                 mqtt_port: int = 1883,  # 修改为标准端口
                 mqtt_user: str = None,
                 mqtt_pass: str = None) -> None:
        logger.bind(tag=TAG).info("初始化MQTT机器人控制核心类（同步版）")

        if getattr(self, '_initialized', False):
            return

        self._is_connected = False
        self._initialized = False
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_pass = mqtt_pass

        self.client_id = f"robot_{uuid.uuid4()}"
        self.client = mqtt.Client(self.client_id)

        # 认证设置
        if mqtt_user and mqtt_pass:
            logger.bind(tag=TAG).info("MQTT机器人控制核心类正在使用认证设置")
            self.client.username_pw_set(mqtt_user, mqtt_pass)

        # 回调绑定
        logger.bind(tag=TAG).info("MQTT机器人控制核心类正在绑定回调函数")
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        try:
            logger.bind(tag=TAG).info(f"正在连接MQTT服务器 {mqtt_host}:{mqtt_port}")
            self.client.connect(mqtt_host, mqtt_port)
            self.client.loop_start()
            # 阻塞等待连接（最多5秒）
            import time
            for _ in range(50):
                if self._is_connected:
                    break
                time.sleep(0.1)
            self._initialized = True
            logger.bind(tag=TAG).info(f"初始化MQTT机器人控制类完成:{getattr(self, '_initialized', False)}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"MQTT连接失败: {str(e)}")

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict, rc: int):
        """连接状态回调"""
        logger.bind(tag=TAG).info(f"MQTT连接状态回调: {mqtt.connack_string(rc)}")
        self._is_connected = rc == 0
        logger.bind(tag=TAG).info(f"MQTT连接{'成功' if rc == 0 else f'失败(代码:{rc})'}")

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int):
        """断开连接回调"""
        logger.bind(tag=TAG).info(f"MQTT断开连接回调: {mqtt.connack_string(rc)}")
        self._is_connected = False
        logger.bind(tag=TAG).error(f"MQTT连接断开(代码:{rc})")

    def send_action(
            self,
            action: str,
            robot_topic: str = "esp32/robot1/sub",
            params: dict = None
    ) -> dict:
        """指令发送方法（同步）"""
        logger.bind(tag=TAG).info(f"发送指令:action={action},robot_topic={robot_topic},params={str(params)}")

        if not self._is_connected:
            logger.bind(tag=TAG).info("MQTT未连接")
            return "ERROR：MQTT未连接"

        if action not in ROBOT_ACTIONS:
            logger.bind(tag=TAG).info(f"无效的动作指令:{action}")
            return f"ERROR:无效的动作指令{action}"

        try:
            payload = action
            result = self.client.publish(robot_topic, payload, 1)  # 设置 QoS=1
            logger.bind(tag=TAG).info(f"发送指令到MQTT服务器：{action}, result={result.rc}")
            return f"SUCCESS:{action}命令执行成功"
        except Exception as e:
            logger.bind(tag=TAG).error(f"指令发送失败: {str(e)}")
            return f"ERROR:{action}命令执行失败"

    def disconnect(self):
        """断开MQTT连接（同步）"""
        if self._is_connected:
            logger.bind(tag=TAG).info("正在断开MQTT连接...")
            self.client.disconnect()
            self.client.loop_stop()
            self._is_connected = False
            logger.bind(tag=TAG).info("MQTT连接已断开")


# 大模型回调接口
ROBOT_CONTROL_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "robots_control",
        "description": "控制机器人执行指定动作",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "forward", "turn_L", "home", "turn_R", "backward",
                        "hello", "omni_walk", "moonwalk_L", "dance", "up_down",
                        "push_up", "front_back", "wave_hand", "scared"
                    ],
                    "description": "四足机器人动作指令说明,每行冒号'：'前面的是机器人指令，后面为指令描述，用户可以通过中英文或者任意语言操作"
                                   "forward：前进指令，控制机器人向前移动;"
                                   "turn_L：左转指令，机器人向左旋转或调整方向;"
                                   "home 归位/复位指令，使机器人回到预设的初始姿态或位置;"
                                   "turn_R：右转指令，机器人向右旋转或调整方向;"
                                   "backward：后退指令，控制机器人向后移动;"
                                   "hello：打招呼动作，可能触发挥手、点头等交互行;"
                                   "omni_walk：全向行走模式，允许机器人向任意方向平移（需全向轮或特殊机械结构支持）;"
                                   "moonwalk_L：月球漫步滑步动作或者星球漫步（模仿迈克尔·杰克逊经典舞步）;"
                                   "dance：舞蹈模式，执行预编程的舞蹈动作序列;"
                                   "up_down：上下起伏动作，可能控制躯干或头部垂直运动;"
                                   "push_up：俯卧撑动作，模拟人体俯卧撑的机械运动（需仿人型机器人）; "
                                   "front_back：前后摆动动作，躯干或肢体前后方向周期性运动;"
                                   "wave_hand：挥手动作，单臂或双臂摆动示意外界;"
                                   "scared：防御/受惊动作，可能触发蜷缩、后退等保护性姿态;"
                },
                "robot_id": {
                    "type": "integer",
                    "default": 1,
                    "description": "机器人ID，默认为1"
                },
                "params": {
                    "type": "object",
                    "default": {},
                    "description": "动作参数"
                }
            },
            "required": ["action"]
        }
    }
}

@register_function('robots_control', ROBOT_CONTROL_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def robots_control(conn, action: str, robot_id: int = 1, params: dict = None):
    """实际执行函数（同步）"""
    logger.bind(tag=TAG).info(f"执行机器人控制指令{action},robot_id={robot_id}")

    try:
        plugin_config = conn.config["plugins"]["robots_control"]
        client_id = plugin_config.get("mqtt_client_id", f"robot_{uuid.uuid4()}")
        mqtt_host = plugin_config.get("mqtt_server", "mqtt.xiaozhi.vip")
        mqtt_port = int(plugin_config.get("mqtt_port", 1883))  # 标准端口
        mqtt_user = plugin_config.get("mqtt_user")
        mqtt_pass = plugin_config.get("mqtt_password")

        # 敏感信息脱敏
        log_pass = "***" if mqtt_pass else ""
        logger.bind(tag=TAG).info(f"MQTT连接信息: host={mqtt_host}, port={mqtt_port}, user={mqtt_user}, pass={log_pass}")

        controller = RobotController(client_id, mqtt_host, mqtt_port, mqtt_user, mqtt_pass)
        if not controller._is_connected:
            return ActionResponse(Action.REQLLM,  "MQTT连接失败，请稍后再试。", None)

        robot_topic = f"esp32/robot{robot_id}/sub"
        logger.bind(tag=TAG).info(f"执行机器人控制指令: action={action}, params={params},robot_topic={robot_topic}")

        result = controller.send_action(action, robot_topic, params)
        logger.bind(tag=TAG).info(f"机器人控制指令执行结果: {result}")

        return ActionResponse(Action.REQLLM, result, None)

    except KeyError as ke:
        logger.bind(tag=TAG).error(f"配置缺失: {str(ke)}")
        return ActionResponse(Action.REQLLM, "缺少必要配置，请检查设置。", None)
    except Exception as e:
        logger.bind(tag=TAG).error(f"执行机器人控制指令失败: {str(e)}")
        return ActionResponse(Action.REQLLM, "执行机器人控制指令失败", None)
    finally:
        logger.bind(tag=TAG).info("MQTT连接已关闭")
