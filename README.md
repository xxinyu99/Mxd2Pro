# Mxd2Pro
将ArcMap的Mxd工程批量自动迁移到ArcGISPro的工程文档中
## 1、自动的将Mxd转到Pro的工程文档中、并展示
1. 模板工程路径 (必须存在一个空白的aprx作为底座)

TEMPLATE_APRX = r"F:\02-study\全自动 MXD 工程迁移\Templates.aprx"

2. MXD 所在的文件夹

INPUT_MXD_FOLDER = r"F:\02-study\全自动 MXD 工程迁移\Demomxd"

3. 结果输出文件夹

OUTPUT_FOLDER = r"F:\02-study\全自动 MXD 工程迁移\Result"

4. 最终工程名称

FINAL_PROJECT_NAME = "Mxd_To_Pro"

5. 需要提前创建一个模板工程、如果没有、请使用上传的Templates.aprx模板
## 2、如果有问题修复工程的数据源
1. 原始工程路径 (脚本绝不会修改这个文件，请放心)

INPUT_APRX = r"F:\Result\Mxd_To_Pro.aprx"

2. 目标数据库 (GDB 或 .sde 连接文件)

TARGET_DB = r"F:\Result\Mxd_To_Pro\Mxd_To_Pro.gdb"

3. 输出的新工程名称后缀 (例如: Mxd_To_Pro_Fixed.aprx)

OUTPUT_SUFFIX = "_Fixed"

4. 智能匹配允许忽略的后缀 (不区分大小写)当找不到精确匹配时，尝试去掉这些后缀再找

IGNORE_SUFFIXES = ["_shp", "_SHP", ".shp", "_merge", "_dissolve", "_New", "Copy"]

