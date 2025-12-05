# -*- coding: utf-8 -*-
import arcpy
import os
import shutil
import time

# ================= 🚀 配置区域 (请修改这里) =================

# 1. 原始工程路径 (脚本绝不会修改这个文件，请放心)
INPUT_APRX = r"F:\Result\Mxd_To_Pro.aprx"

# 2. 目标数据库 (GDB 或 .sde 连接文件)
TARGET_DB = r"F:\Result\Mxd_To_Pro\Mxd_To_Pro.gdb"

# 3. 输出的新工程名称后缀 (例如: Mxd_To_Pro_Fixed.aprx)
OUTPUT_SUFFIX = "_Fixed"

# 4. 智能匹配允许忽略的后缀 (不区分大小写)
# 当找不到精确匹配时，尝试去掉这些后缀再找
IGNORE_SUFFIXES = ["_shp", "_SHP", ".shp", "_merge", "_dissolve", "_New", "Copy"]


# ==========================================================

class SafeUpdater:
    def __init__(self, input_aprx, target_db):
        self.input_aprx = input_aprx
        self.target_db = target_db
        self.working_aprx_path = ""  # 将在运行时生成
        self.db_inventory = {}  # 数据库索引缓存
        self.logs = []  # 记录日志以便最后统计

    def log(self, msg, level="INFO"):
        """实时打印并存储日志"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        full_msg = f"[{timestamp}] [{level}] {msg}"
        print(full_msg)
        if level in ["ERROR", "WARNING"]:
            self.logs.append(full_msg)

    def prepare_working_copy(self):
        """【安全核心】先物理复制文件，确保原文件绝对安全"""
        folder = os.path.dirname(self.input_aprx)
        filename = os.path.basename(self.input_aprx)
        name, ext = os.path.splitext(filename)

        # 构建新文件名
        new_filename = f"{name}{OUTPUT_SUFFIX}{ext}"
        self.working_aprx_path = os.path.join(folder, new_filename)

        self.log(f"正在创建作业副本...")
        self.log(f"源文件: {self.input_aprx}")
        self.log(f"新文件: {self.working_aprx_path}")

        try:
            # 使用 shutil 进行系统级复制，比 arcpy saveACopy 更稳健
            shutil.copy2(self.input_aprx, self.working_aprx_path)
            self.log("副本创建成功，后续所有操作将只针对新文件进行。")
            return True
        except Exception as e:
            self.log(f"创建副本失败，停止运行: {e}", "ERROR")
            return False

    def index_target_db(self):
        """预读取目标数据库，建立内存索引 (极大提升速度)"""
        self.log("正在扫描目标数据库内容...")

        # 记录原始环境，防止干扰
        orig_env = arcpy.env.workspace
        arcpy.env.workspace = self.target_db

        try:
            # 获取所有 FeatureClasses 和 Tables
            items = arcpy.ListFeatureClasses() + arcpy.ListTables()

            if not items:
                self.log("目标数据库为空！无法进行更新。", "ERROR")
                return False

            for item in items:
                # 存两份索引：
                # 1. 真实全名 (用于最终赋值)
                # 2. 小写短名 (用于忽略 SDE 前缀和大小写匹配)
                #    例如 SDE 中是 "sde.owner.Roads"，短名存为 "roads"
                self.db_inventory[item] = item

                short_name = item.split('.')[-1].lower()
                self.db_inventory[short_name] = item

            self.log(f"索引建立完成，共发现 {len(items)} 个数据集。")
            return True

        except Exception as e:
            self.log(f"读取数据库失败: {e}", "ERROR")
            return False
        finally:
            arcpy.env.workspace = orig_env

    def smart_match_dataset(self, old_dataset_name, layer_name):
        """
        智能匹配算法
        返回: (匹配到的真实名称, 匹配方法描述)
        """
        if not old_dataset_name:
            return None, "旧数据源名称为空"

        name_lower = old_dataset_name.lower()

        # 1. 尝试：精确/忽略大小写/忽略SDE前缀 匹配
        # 直接查短名索引 (涵盖了 Roads -> sde.Roads 的情况)
        short_name = name_lower.split('.')[-1]
        if short_name in self.db_inventory:
            return self.db_inventory[short_name], "名称匹配(含SDE前缀处理)"

        # 2. 尝试：清理后缀 (例如 Roads_shp -> Roads)
        for suffix in IGNORE_SUFFIXES:
            s_lower = suffix.lower()
            if short_name.endswith(s_lower):
                cleaned = short_name.replace(s_lower, "")
                if cleaned in self.db_inventory:
                    return self.db_inventory[cleaned], f"去除后缀 '{suffix}'"

        # 3. 尝试：匹配图层名称 (作为最后的备选)
        # 比如数据源叫 Export_Output，但图层名叫 District
        lyr_short = layer_name.lower()
        if lyr_short in self.db_inventory:
            return self.db_inventory[lyr_short], "匹配图层在目录窗格的名称"

        return None, None

    def execute(self):
        # 1. 准备副本
        if not self.prepare_working_copy(): return

        # 2. 索引数据库
        if not self.index_target_db(): return

        # 3. 打开副本工程
        try:
            aprx = arcpy.mp.ArcGISProject(self.working_aprx_path)
        except Exception as e:
            self.log(f"无法打开工程文件: {e}", "ERROR")
            return

        update_count = 0
        fail_count = 0

        # 4. 遍历
        for m in aprx.listMaps():
            self.log(f"--- 正在处理地图: {m.name} ---")

            # 处理图层 + 表格
            all_layers = m.listLayers() + m.listTables()

            for lyr in all_layers:
                # 过滤不支持的图层
                if not hasattr(lyr, "connectionProperties") or not lyr.supports("CONNECTIONPROPERTIES"):
                    continue

                try:
                    cp = lyr.connectionProperties
                    # 检查是否是合法的数据连接
                    if not cp or 'connection_info' not in cp or 'dataset' not in cp:
                        continue

                    old_ws = cp['connection_info'].get('database', '未知路径')
                    old_ds = cp.get('dataset', '未知数据')

                    # 检查是否已经是目标路径 (路径标准化比较)
                    if old_ws != '未知路径':
                        if os.path.normpath(str(old_ws)).lower() == os.path.normpath(self.target_db).lower():
                            continue  # 已连接，跳过

                    # === 寻找新数据源 ===
                    new_ds_name, match_method = self.smart_match_dataset(old_ds, lyr.name)

                    if not new_ds_name:
                        self.log(f"[跳过] {lyr.name}: 目标库中未找到对应数据 (原: {old_ds})", "WARNING")
                        fail_count += 1
                        continue

                    # === 执行更新 ===
                    # 构造新的连接属性字典
                    new_cp = cp.copy()
                    new_cp['connection_info']['database'] = self.target_db
                    new_cp['dataset'] = new_ds_name

                    print(f"  > 正在修复: {lyr.name}")
                    print(f"    原: {old_ds} | 新: {new_ds_name} ({match_method})")

                    lyr.updateConnectionProperties(lyr.connectionProperties, new_cp)

                    if lyr.isBroken:
                        self.log(f"[失败] {lyr.name}: 路径已修改但连接断开 (可能是字段定义不匹配)", "ERROR")
                        fail_count += 1
                    else:
                        self.log(f"[成功] {lyr.name} 已修复")
                        update_count += 1

                except Exception as e:
                    self.log(f"[异常] 处理 {lyr.name} 时出错: {str(e)}", "ERROR")
                    fail_count += 1

        # 5. 保存并总结
        if update_count > 0:
            aprx.save()  # 直接保存到那个副本里
            self.log("=" * 60)
            self.log(f"任务结束。")
            self.log(f"成功修复: {update_count} 个图层")
            self.log(f"修复失败: {fail_count} 个图层")
            self.log(f"结果已保存至: {self.working_aprx_path}")
            self.log("=" * 60)
        else:
            self.log("未进行任何修改，删除临时副本...")
            del aprx
            try:
                os.remove(self.working_aprx_path)
                self.log("已清理未修改的副本。")
            except:
                pass

        # 6. 输出错误汇总
        if self.logs:
            print("\n--- ⚠️ 异常/警告汇总 ---")
            for l in self.logs:
                print(l)


if __name__ == "__main__":
    tool = SafeUpdater(INPUT_APRX, TARGET_DB)
    tool.execute()