# -*- coding: utf-8 -*-
import arcpy
import os
import sys
import datetime
import traceback

# ================= 配置区域 =================

# 1. 模板工程路径 (必须存在一个空白的aprx作为底座)
TEMPLATE_APRX = r"F:\02-study\全自动 MXD 工程迁移\Templates.aprx"

# 2. MXD 所在的文件夹
INPUT_MXD_FOLDER = r"F:\02-study\全自动 MXD 工程迁移\Demomxd"

# 3. 结果输出文件夹
OUTPUT_FOLDER = r"F:\02-study\全自动 MXD 工程迁移\Result"

# 4. 最终工程名称
FINAL_PROJECT_NAME = "Mxd_To_Pro"

# ===========================================

# 全局日志容器
LOG_CONTAINER = []


def log(message, level="INFO"):
    """
    日志记录函数：同时打印到控制台并存入内存列表
    """
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] [{level}] {message}"
    print(full_msg)
    LOG_CONTAINER.append(full_msg)


def save_log_to_file(output_folder):
    """
    将日志保存到txt文件
    """
    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_folder, f"Migration_Report_{date_str}.txt")
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(LOG_CONTAINER))
        print(f"\n📄 日志文件已生成: {log_file}")
    except Exception as e:
        print(f"❌ 无法保存日志文件: {e}")


def safe_rename(name):
    """清理非法字符"""
    return "".join(x for x in name if x.isalnum() or x in "_")


def copy_and_repath_layer(layer, target_gdb, source_tracker):
    """核心数据拷贝与重定向逻辑"""
    try:
        if not layer.supports("CONNECTIONPROPERTIES"):
            return

        conn_props = layer.connectionProperties

        if not conn_props or 'connection_info' not in conn_props:
            return

        workspace = conn_props.get('connection_info', {}).get('database')
        dataset_name = conn_props.get('dataset')

        if not workspace or not dataset_name:
            return

        full_source_path = os.path.join(workspace, dataset_name)
        target_name = ""

        # --- 数据入库 ---
        if full_source_path in source_tracker:
            target_name = source_tracker[full_source_path]
            # log(f"    [复用] {dataset_name} -> {target_name}", "DEBUG")
        else:
            base_name = os.path.splitext(dataset_name)[0]
            clean_name = safe_rename(base_name)
            target_path = os.path.join(target_gdb, clean_name)

            counter = 1
            while arcpy.Exists(target_path):
                clean_name = f"{safe_rename(base_name)}_{counter}"
                target_path = os.path.join(target_gdb, clean_name)
                counter += 1

            # 仅当源文件存在时才拷贝
            if os.path.exists(full_source_path) or arcpy.Exists(full_source_path):
                log(f"    [拷贝] {dataset_name} -> {clean_name}", "INFO")
                try:
                    if layer.isFeatureLayer:
                        arcpy.management.CopyFeatures(layer, target_path)
                    elif layer.isRasterLayer:
                        arcpy.management.CopyRaster(layer, target_path)
                    else:
                        arcpy.management.Copy(full_source_path, target_path)

                    source_tracker[full_source_path] = clean_name
                    target_name = clean_name
                except Exception as e:
                    log(f"    ❌ 拷贝失败 [{layer.name}]: {e}", "ERROR")
                    return

        # --- 重定向连接 ---
        if target_name:
            new_conn_props = {
                'connection_info': {'database': target_gdb},
                'dataset': target_name,
                'workspace_factory': 'File Geodatabase'
            }
            try:
                layer.updateConnectionProperties(layer.connectionProperties, new_conn_props)
            except Exception as e:
                log(f"    ⚠️ 重定向失败 [{layer.name}]: {e}", "WARNING")

    except Exception as e:
        log(f"    ⚠️ 图层处理异常 [{layer.name}]: {e}", "WARNING")


def main():
    log("🚀 任务启动...", "INFO")

    # 0. 基础检查
    if not os.path.exists(TEMPLATE_APRX):
        log(f"❌ 错误：找不到模板文件: {TEMPLATE_APRX}", "ERROR")
        save_log_to_file(OUTPUT_FOLDER)
        return

    # 1. 加载底座
    log(f"🔄 正在加载模板工程: {TEMPLATE_APRX}", "INFO")
    aprx = arcpy.mp.ArcGISProject(TEMPLATE_APRX)

    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    # 2. 准备 GDB
    gdb_name = f"{FINAL_PROJECT_NAME}_Data.gdb"
    target_gdb_path = os.path.join(OUTPUT_FOLDER, gdb_name)
    if not arcpy.Exists(target_gdb_path):
        arcpy.management.CreateFileGDB(OUTPUT_FOLDER, gdb_name)
        log(f"📦 新建数据库: {target_gdb_path}", "SUCCESS")
    else:
        log(f"📦 使用现有数据库: {target_gdb_path}", "INFO")

    mxd_files = [f for f in os.listdir(INPUT_MXD_FOLDER) if f.lower().endswith(".mxd")]
    source_tracker = {}

    log(f"📄 发现 {len(mxd_files)} 个MXD待处理\n", "INFO")

    # 3. 循环处理
    for mxd_file in mxd_files:
        mxd_path = os.path.join(INPUT_MXD_FOLDER, mxd_file)
        mxd_basename = os.path.splitext(mxd_file)[0]

        log(f"=== 处理 MXD: {mxd_basename} ===", "INFO")

        try:
            # 记录导入前的状态
            pre_maps = {m.name for m in aprx.listMaps()}
            pre_layouts = {l.name for l in aprx.listLayouts()}

            # 导入
            aprx.importDocument(mxd_path)

            # 识别新增项
            current_layouts = aprx.listLayouts()
            current_maps = aprx.listMaps()

            new_layouts = [l for l in current_layouts if l.name not in pre_layouts]
            # 获取所有新增地图（包含可能的空白地图）
            raw_new_maps = [m for m in current_maps if m.name not in pre_maps]

            # ---------------------------------------------------------
            # 筛选有效地图，剔除空地图
            # ---------------------------------------------------------
            valid_new_maps = []
            for mp in raw_new_maps:
                try:
                    # 检查图层数量
                    if len(mp.listLayers()) == 0:
                        del_name = mp.name  # 先记下名字
                        aprx.deleteItem(mp)  # 后删除
                        log(f"  🗑️ 删除空地图: {del_name}", "INFO")
                    else:
                        valid_new_maps.append(mp)
                except Exception as e:
                    log(f"  ⚠️ 检查地图时出错: {e}", "WARNING")

            # 如果剔除后没有剩下的地图，说明这个MXD全是空的
            if not valid_new_maps and not new_layouts:
                log("  ⚠️ 该文件导入后无有效内容，跳过。", "WARNING")
                continue

            # --- A. 处理布局 ---
            for i, layout in enumerate(new_layouts):
                layout.name = mxd_basename if i == 0 else f"{mxd_basename}_{i + 1}"
                log(f"  ✅ Layout重命名: {layout.name}", "SUCCESS")

            # --- B. 处理地图 ---
            for mp in valid_new_maps:
                old_name = mp.name
                new_name = f"{mxd_basename}_{old_name}"
                mp.name = new_name
                log(f"  ✅ Map重命名: {new_name}", "SUCCESS")

                # 处理图层数据
                for layer in mp.listLayers():
                    if not layer.isGroupLayer:
                        copy_and_repath_layer(layer, target_gdb_path, source_tracker)

        except Exception as e:
            # 打印详细错误堆栈，方便排查“未知错误”
            tb_msg = traceback.format_exc()
            log(f"❌ 处理 {mxd_basename} 时发生严重错误:\n{tb_msg}", "ERROR")

        # log("-" * 30)

    # 4. 最终清理
    log("\n🧹 执行最终清理...", "INFO")
    for m in aprx.listMaps():
        # 如果地图名字是默认的"Map"且为空，或者有坏图层
        try:
            if len(m.listLayers()) == 0:
                del_name = m.name  # 先缓存名字
                aprx.deleteItem(m)
                log(f"  🗑️ 清理残留空地图: {del_name}", "INFO")
        except Exception as e:
            # 这里的报错不影响大局，记录一下即可
            pass

    # 5. 保存结果
    final_aprx_path = os.path.join(OUTPUT_FOLDER, f"{FINAL_PROJECT_NAME}.aprx")
    log(f"\n💾 正在保存: {final_aprx_path}", "INFO")
    try:
        aprx.saveACopy(final_aprx_path)
        log("✨✨✨ 全部处理完成！ ✨✨✨", "SUCCESS")
    except Exception as e:
        log(f"❌ 保存工程失败: {e}", "ERROR")

    # 6. 生成日志文件
    save_log_to_file(OUTPUT_FOLDER)


if __name__ == '__main__':
    main()