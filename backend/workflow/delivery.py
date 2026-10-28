"""A small, explicit output contract for product advice without research evidence."""
from pydantic import BaseModel, Field


class OfflineProduct(BaseModel):
    product: str = Field(min_length=3, max_length=120)
    target_user: str = Field(min_length=3, max_length=160)
    use_example: str = Field(min_length=20, max_length=600)
    reason_hypotheses: list[str] = Field(min_length=1, max_length=3)
    minimal_features: list[str] = Field(min_length=1, max_length=3)
    excluded_features: list[str] = Field(min_length=1, max_length=4)
    competitor_names_to_check: list[str] = Field(min_length=1, max_length=5)
    first_experiment: str = Field(min_length=20, max_length=500)


OFFLINE_DELIVERY = '''你是产品结论编辑。只根据真实需求做一个暂定选择，输出指定JSON。
本次完全没有检索来源。草稿及模拟评审里的竞品缺点、市场观察、用户付费偏好不是事实，不能引用为证据。
把结果写成具体、简短、可理解的产品建议，不再写架构报告。可否定草稿中不符合约束的功能。
use_example只写用户主动输入什么、操作什么、最终得到什么；不得编造无法离线粘贴等场景。
reason_hypotheses只写这个具体产品可能解决的困难，不评论竞品缺陷，不宣称用户普遍有此需求。
minimal_features最多3项具体功能；用户要容易开发管理时，去掉后台监听、社区撮合、云同步、AI估价等依赖。
excluded_features明确不做什么以缩小维护量。
competitor_names_to_check只填你知道的产品名称或手工替代办法，不填功能、缺点或市场份额。不能说没竞品。
first_experiment给一个小规模人工测试：测试对象、操作、观察指标、放弃条件；阈值明确是暂定决策线。
不能宣称已检索、已观察市场、合规保证、绝对安全、市场空白、竞品稀少或已证明商业价值。
不要把开发者偏好开源推断成终端用户愿意为开源付费。总计约600汉字。'''


def render_offline_product(product, language='zh'):
    bullets = lambda values: '\n'.join('- ' + value for value in values)
    # Do not retain unsupported comparisons smuggled into the "hypotheses"
    # field. Competitors have a separate names-only, explicitly unverified list.
    comparison_terms = ['竞品', '现有产品', '替代品', '备忘录', '云笔记', '市场空白',
        '填补空白', '绝对安全', '已验证', '已调研'] + product.competitor_names_to_check
    if language == 'en':
        comparison_terms += ['competitor', 'existing product', 'market gap']
    reasons = [reason for reason in product.reason_hypotheses
        if not any(term.lower() in reason.lower() for term in comparison_terms)]
    if language == 'en':
        reasons = reasons or ['Whether this need is frequent, and whether current options are enough, has to be checked with a small test.']
        return (f'## Provisional recommendation: {product.product}\n\n'
            f'**Who it is for:** {product.target_user}\n\n'
            f'### What it is used for\n\n{product.use_example}\n\n'
            '### Why it might be worth trying (unverified assumptions)\n\n' + bullets(reasons) + '\n\n'
            '### First version only\n\n' + bullets(product.minimal_features) + '\n\n'
            '### Left out so it stays maintainable\n\n' + bullets(product.excluded_features) + '\n\n'
            '### Similar products\n\nThese names still need to be checked:\n\n' +
            bullets(product.competitor_names_to_check) + '\n\n'
            '**This run did not search the web. It cannot show that similar products are rare, or that those products lack a feature. The “few competitors” requirement is not verified.**\n\n'
            '### How to decide whether it is worth building\n\n' + product.first_experiment + '\n\nThese thresholds are a provisional decision line, not an industry standard.\n\n'
            'This is one concrete candidate, not a verified business opportunity. Demand, differentiation, and willingness to pay are still unknown.')
    reasons = reasons or ['这项需求是否高频、现有办法是否够用，需要先通过小规模测试确认。']
    return (f'## 暂定推荐：{product.product}\n\n'
        f'**目标用户：** {product.target_user}\n\n'
        f'### 用它做什么\n\n{product.use_example}\n\n'
        '### 为什么考虑做（待验证假设）\n\n' + bullets(reasons) + '\n\n'
        '### 第一版只做这些\n\n' + bullets(product.minimal_features) + '\n\n'
        '### 为了容易维护，暂不做\n\n' + bullets(product.excluded_features) + '\n\n'
        '### 同类产品有没有\n\n以下仅是待核实的竞品或替代办法名称：\n\n' +
        bullets(product.competitor_names_to_check) + '\n\n'
        '**本次未联网，不能据此判断同类产品少，也不能证明上述产品缺少某项功能。竞争稀少这一要求尚未验证。**\n\n'
        '### 下一步怎么判断值不值得做\n\n' + product.first_experiment + '\n\n以上阈值只是暂定决策线，不是行业标准。\n\n'
        '这是一个具体候选，不是已验证的商业机会；需求强度、差异化和付费意愿仍未知。')
