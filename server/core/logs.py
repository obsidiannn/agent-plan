import logging

# 日志配置
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler1 = logging.StreamHandler()
handler2 = logging.FileHandler(filename='./log.log')
formatter = logging.Formatter(
    "%(asctime)s - %(module)s - %(funcName)s - line:%(lineno)d - %(levelname)s - %(message)s"
)
handler1.setFormatter(formatter)
handler2.setFormatter(formatter)
logger.addHandler(handler1)  # 将日志输出至屏幕
logger.addHandler(handler2)  # 将日志输出至文件