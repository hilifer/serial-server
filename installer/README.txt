================================================
  耀嵘光储充管理系统 — 安装说明
================================================

【前提条件】
  - Windows 10/11
  - Python 3.10+ (安装时勾选 "Add Python to PATH")
  - 下载地址：https://www.python.org/downloads/

【方式一：绿色安装（推荐）】
  1. 解压本压缩包到任意目录（如 D:\耀嵘\）
  2. 双击 install.bat（自动安装依赖 + 创建桌面快捷方式）
  3. 以后双击桌面上的"耀嵘光储充管理系统"即可启动

【方式二：EXE安装包】
  需要 Inno Setup 编译 installer\setup.iss 生成安装程序
  下载 Inno Setup：https://jrsoftware.org/isdl.php

【使用】
  启动后自动打开浏览器：
  - 停车场监控：http://localhost:8000/
  - 能源看板：  http://localhost:8000/detail.html
  - 电表详情：  点击流向图中的节点

【串口配置】
  编辑 config.yaml 修改串口参数：
  - COM31: 停车场A区 (车位探测器)
  - COM32: 停车场B区 (车位探测器)
  - COM33: 电表 (Modbus RTU)

【停止服务】
  在命令行窗口按 Ctrl+C

【卸载】
  删除安装目录即可（绿色安装无注册表残留）
