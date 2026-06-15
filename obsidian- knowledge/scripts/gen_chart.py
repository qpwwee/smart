#!/usr/bin/env python3
"""
图表生成脚本 - 为 LLM Wiki 生成 matplotlib 图表
用法: python3 gen_chart.py --type bar --data "label1:10,label2:20,label3:15" --output chart.png --title "示例图表"
"""

import matplotlib.pyplot as plt
import argparse
import os
from urllib.parse import unquote

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

def parse_data(data_str):
    """解析 'label1:10,label2:20' 格式的数据"""
    items = {}
    for item in data_str.split(','):
        if ':' in item:
            label, value = item.split(':', 1)
            try:
                items[label.strip()] = float(value.strip())
            except ValueError:
                items[label.strip()] = value.strip()
    return items

def generate_bar(data, output, title, xlabel=None, ylabel=None):
    """生成柱状图"""
    labels = list(data.keys())
    values = list(data.values())

    plt.figure(figsize=(10, 6))
    plt.bar(labels, values, color='steelblue')
    plt.title(title, fontsize=14, fontweight='bold')

    if xlabel:
        plt.xlabel(xlabel, fontsize=12)
    if ylabel:
        plt.ylabel(ylabel, fontsize=12)

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"图表已保存: {output}")

def generate_line(data, output, title, xlabel=None, ylabel=None):
    """生成折线图"""
    labels = list(data.keys())
    values = list(data.values())

    plt.figure(figsize=(10, 6))
    plt.plot(labels, values, marker='o', linewidth=2, markersize=8, color='steelblue')
    plt.title(title, fontsize=14, fontweight='bold')

    if xlabel:
        plt.xlabel(xlabel, fontsize=12)
    if ylabel:
        plt.ylabel(ylabel, fontsize=12)

    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"图表已保存: {output}")

def generate_pie(data, output, title):
    """生成饼图"""
    labels = list(data.keys())
    values = list(data.values())

    plt.figure(figsize=(8, 8))
    plt.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    plt.title(title, fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"图表已保存: {output}")

def main():
    parser = argparse.ArgumentParser(description='为 LLM Wiki 生成图表')
    parser.add_argument('--type', choices=['bar', 'line', 'pie'], default='bar', help='图表类型')
    parser.add_argument('--data', required=True, help='数据，格式: label1:value1,label2:value2')
    parser.add_argument('--output', required=True, help='输出文件名')
    parser.add_argument('--title', required=True, help='图表标题')
    parser.add_argument('--xlabel', help='X轴标签')
    parser.add_argument('--ylabel', help='Y轴标签')

    args = parser.parse_args()

    # 解码中文参数
    data = parse_data(unquote(args.data))
    title = unquote(args.title)
    xlabel = unquote(args.xlabel) if args.xlabel else None
    ylabel = unquote(args.ylabel) if args.ylabel else None

    # 确定输出路径 (raw/assets/)
    vault_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets_dir = os.path.join(vault_path, 'raw', 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    output_path = os.path.join(assets_dir, args.output)

    # 生成图表
    if args.type == 'bar':
        generate_bar(data, output_path, title, xlabel, ylabel)
    elif args.type == 'line':
        generate_line(data, output_path, title, xlabel, ylabel)
    elif args.type == 'pie':
        generate_pie(data, output_path, title)

if __name__ == '__main__':
    main()