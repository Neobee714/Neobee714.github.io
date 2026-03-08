import re
import codecs

path = 'e:/Program/Blog-2/templates/base.html'
with codecs.open(path, 'r', 'utf-8') as f:
    content = f.read()

# CSS extraction regex
pattern = r'    /\* === 全局搜索 Modal 样式 \(Spotlight Search\) === \*/(.*?)</style>'
match = re.search(pattern, content, re.DOTALL)

if match:
    extracted_css = '    /* === 全局搜索 Modal 样式 (Spotlight Search) === */' + match.group(1)
    
    # 1. Append to base.css
    with codecs.open('e:/Program/Blog-2/static/css/base.css', 'a', 'utf-8') as f:
        f.write('\n\n' + extracted_css)
        
    # 2. Replace in base.html
    new_style_block = """  <style>
    :root {
      --font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif;
      --font-mono: 'JetBrains Mono', ui-monospace, monospace;

      /* 默认亮色主题变量 (lofi 等) */
      --primary-color: #10b981;
      --secondary-color: #6366f1;
      --accent-color: #f59e0b;

      --sidebar-bg: #f8fafc;
      --code-bg: #f1f5f9;
      --code-header-bg: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
      --code-border: rgba(0, 0, 0, 0.05);

      --glass-bg: rgba(255, 255, 255, 0.8);
      --glass-border: rgba(0, 0, 0, 0.05);
      --glass-text-strong: #1f2937;
      --glass-text-dim: #6b7280;
    }

    /* 暗色主题变量重写 (business) */
    :root[data-theme="business"] {
      --primary-color: #10b981;
      --secondary-color: #6366f1;
      --accent-color: #f59e0b;

      --sidebar-bg: #0e1015;
      --code-bg: #15171e;
      --code-header-bg: linear-gradient(135deg, #1c1f26 0%, #22262f 100%);
      --code-border: rgba(255, 255, 255, 0.08);

      --glass-bg: rgba(26, 28, 36, 0.7);
      --glass-border: rgba(255, 255, 255, 0.05);
      --glass-text-strong: #e5e7eb;
      --glass-text-dim: #9ca3af;
    }

    body {
      font-family: var(--font-sans);
    }
  </style>"""
  
    content = re.sub(r'  <style>.*?</style>', new_style_block, content, flags=re.DOTALL)
    
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(content)
        
    print("Extraction successful!")
else:
    print("Could not find the styles to extract.")
