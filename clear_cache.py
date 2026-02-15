#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清除缓存脚本 (Clear Cache Script)
用于清除 Flask 应用的所有缓存
"""
import os
import shutil
import sys

def clear_cache():
    """清除所有缓存目录"""
    cache_dirs = [
        'flask_cache',
        '__pycache__',
        'services/__pycache__',
    ]

    cleared = []
    errors = []

    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                cleared.append(cache_dir)
                print(f"[OK] 已清除: {cache_dir}")
            except Exception as e:
                errors.append((cache_dir, str(e)))
                print(f"[ERROR] 清除失败: {cache_dir} - {str(e)}")
        else:
            print(f"[SKIP] 不存在: {cache_dir}")

    print("\n" + "=" * 50)
    if cleared:
        print(f"成功清除 {len(cleared)} 个缓存目录")
    if errors:
        print(f"失败 {len(errors)} 个")
        return 1
    else:
        print("缓存清除完成！")
        return 0

if __name__ == "__main__":
    sys.exit(clear_cache())
