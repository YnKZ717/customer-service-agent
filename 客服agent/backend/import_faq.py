"""解析操作手册md，灌入approved_faqs.json"""
import json, re, shutil, os, sys

sys.stdout.reconfigure(encoding='utf-8')

faq_md_path = r'D:\privateforyge\customer-service-agent\客服agent相关\faq\常见问题解决方案\常见问题解决方案.md'
faq_img_dir = r'D:\privateforyge\customer-service-agent\客服agent相关\faq\常见问题解决方案\图片和附件'
faq_img_target = r'D:\privateforyge\customer-service-agent\客服agent\backend\faq-images'

with open(faq_md_path, 'r', encoding='utf-8') as f:
    content = f.read()

sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
sections = [s.strip() for s in sections if s.strip()]

new_faqs = []

category_map = {
    '真人卡审核': 'content_policy',
    '敏感信息拦截': 'content_policy',
    '版权限制拦截': 'copyright',
    '视频或节点丢失': 'platform',
    '视频中包含字幕': 'video_generation',
    '视频中有水印': 'video_generation',
    '视频风格漂移': 'video_generation',
    '双胞胎问题': 'video_generation',
    '中文发音不准': 'video_generation',
    '提示词教程': 'usage',
    '智能体生成到一半卡住': 'bug',
    '积分发放与过期': 'billing',
    '协作画布积分不足': 'billing',
}

image_counter = 0

for section in sections:
    lines = section.split('\n')
    if not lines[0].startswith('## '):
        continue

    title = lines[0][3:].strip()
    category = category_map.get(title, 'usage')

    body = '\n'.join(lines[1:]).strip()

    images = []
    for img_match in re.finditer(r'!\[.*?\]\((.+?)\)', body):
        img_rel_path = img_match.group(1)
        img_file = img_rel_path.replace('图片和附件/', '')
        img_file = img_file.replace('%20', ' ')

        src_path = os.path.join(faq_img_dir, img_file)

        image_counter += 1
        ext = os.path.splitext(img_file)[1]
        safe_title = re.sub(r'[^\w]', '_', title)
        new_name = f'faq_{safe_title}_{image_counter}{ext}'
        new_name = re.sub(r'_+', '_', new_name).strip('_')

        dst_path = os.path.join(faq_img_target, new_name)
        if os.path.exists(src_path):
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
            images.append(new_name)
            print(f'  复制图片: {img_file} -> {new_name}')
        else:
            print(f'  图片不存在: {src_path}')

    answer = re.sub(r'!\[.*?\]\(.+?\)', '', body)
    answer = re.sub(r'\*\*', '', answer)
    answer = answer.replace('\\', '')
    answer = answer.strip()
    answer = re.sub(r'\n{3,}', '\n\n', answer)

    if answer:
        new_faqs.append({
            'question': title,
            'answer': answer,
            'category': category,
            'images': images,
        })
        print(f'\n[{category}] {title} ({len(images)}张图)')
        print(f'  答案前80字: {answer[:80]}...')

existing_path = r'D:\privateforyge\customer-service-agent\客服agent\backend\approved_faqs.json'
with open(existing_path, 'r', encoding='utf-8') as f:
    existing_faqs = json.load(f)

existing_faqs.extend(new_faqs)

with open(existing_path, 'w', encoding='utf-8') as f:
    json.dump(existing_faqs, f, ensure_ascii=False, indent=2)

print(f'\n完成！新增 {len(new_faqs)} 条FAQ，总计 {len(existing_faqs)} 条')
