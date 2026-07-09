/**
 * 节日主题配置 —— 每个节日独立的视觉、文案、动画、装饰
 *
 * 与后端返回的 FestivalConfig 通过节日名称（name）进行匹配。
 * 主题只负责前端展示层，额度逻辑仍由后端驱动。
 */

export type FestivalAnimationType =
  | 'fireworks'
  | 'lanterns'
  | 'dragon_boat'
  | 'milky_way'
  | 'moon_rise'
  | 'climbing'
  | 'new_year_fireworks'
  | 'gears'
  | 'flag_fireworks'
  | 'hearts_rise'
  | 'snowfall'
  | 'sprout'
  | 'sun_pulse'
  | 'maple_fall'
  | 'snow_warm'
  | 'national_day'
  | 'starfield_fireworks'
  | 'code_rain'
  | 'nebula'

export interface FestivalTheme {
  id: string
  name: string
  title: string
  emoji: string
  poem: string
  poemAuthor: string
  message: string
  gradient: string
  borderColor: string
  titleColor: string
  textColor: string
  amountColor: string
  amountGlow: string
  buttonGradient: string
  buttonTextColor: string
  buttonShadow: string
  taglineColor: string
  particleColors: string[]
  animationType: FestivalAnimationType
  decoration: string
  fontFamily?: string
  buttonText: string
  specialEffect?: string
}

export const FESTIVAL_THEMES: FestivalTheme[] = [
  {
    id: 'spring_festival',
    name: '春节',
    title: '新春大吉',
    emoji: '🎊',
    poem: '爆竹声中一岁除，春风送暖入屠苏',
    poemAuthor: '王安石《元日》',
    message: '在这辞旧迎新的时刻，愿星光为你指引前路。OmicHub 送你 {amount} 额度，开启新一年的探索之旅！',
    gradient: 'linear-gradient(145deg, #1a0505 0%, #2d0a0a 40%, #1a0508 100%)',
    borderColor: 'rgba(255,215,0,0.45)',
    titleColor: '#FFD700',
    textColor: '#ffe4c4',
    amountColor: '#FFD700',
    amountGlow: '0 0 40px rgba(255,215,0,0.6), 0 0 80px rgba(255,215,0,0.2)',
    buttonGradient: 'linear-gradient(135deg, #c41e1e 0%, #e83030 100%)',
    buttonTextColor: '#FFD700',
    buttonShadow: '0 0 20px rgba(255,50,50,0.5)',
    taglineColor: '#d4a574',
    particleColors: ['#FFD700', '#FF6B35', '#FF4444', '#FFA500'],
    animationType: 'starfield_fireworks',
    decoration: 'spring_couplets',
    buttonText: '领取新年红包 🧧',
  },
  {
    id: 'lantern_festival',
    name: '元宵节',
    title: '元宵喜乐',
    emoji: '🏮',
    poem: '众里寻他千百度，蓦然回首，那人却在，灯火阑珊处',
    poemAuthor: '辛弃疾《青玉案·元夕》',
    message: '花灯如昼，月圆人团圆。每一盏灯笼都是一颗坠落的星星，照亮我们短暂而美丽的旅程。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #1a1008 0%, #2d1f12 40%, #1a140a 100%)',
    borderColor: 'rgba(255,165,0,0.4)',
    titleColor: '#FFA500',
    textColor: '#ffe8d6',
    amountColor: '#FFB347',
    amountGlow: '0 0 40px rgba(255,165,0,0.5)',
    buttonGradient: 'linear-gradient(135deg, #e8780a 0%, #ff9f2e 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(255,165,0,0.4)',
    taglineColor: '#d4a574',
    particleColors: ['#FFA500', '#FFD700', '#FF8C00', '#FFB347'],
    animationType: 'lanterns',
    decoration: 'lanterns',
    buttonText: '收下这份星光 ✨',
  },
  {
    id: 'dragon_boat',
    name: '端午节',
    title: '端午安康',
    emoji: '🐲',
    poem: '路漫漫其修远兮，吾将上下而求索',
    poemAuthor: '屈原《离骚》',
    message: '粽叶飘香，龙舟竞渡。我们如原子般短暂汇聚，又终将散入星河。送你 {amount} 额度，端午安康！',
    gradient: 'linear-gradient(145deg, #081a10 0%, #122d1f 40%, #0a1a12 100%)',
    borderColor: 'rgba(0,200,150,0.4)',
    titleColor: '#4ECDC4',
    textColor: '#d4f5e9',
    amountColor: '#4ECDC4',
    amountGlow: '0 0 40px rgba(78,205,196,0.5)',
    buttonGradient: 'linear-gradient(135deg, #0d8a6a 0%, #1aad8a 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(0,200,150,0.4)',
    taglineColor: '#6ab09a',
    particleColors: ['#4ECDC4', '#44A08D', '#96E6A1', '#00C896'],
    animationType: 'dragon_boat',
    decoration: 'bamboo',
    buttonText: '领取 🎋',
  },
  {
    id: 'qixi',
    name: '七夕节',
    title: '七夕快乐',
    emoji: '💕',
    poem: '两情若是久长时，又岂在朝朝暮暮',
    poemAuthor: '秦观《鹊桥仙》',
    message: '在浩瀚宇宙中相遇，是千万分之一的奇迹。就像两颗原子在星云中偶然碰撞，绽放出独特的光芒。送你 {amount} 额度～',
    gradient: 'linear-gradient(145deg, #1a0820 0%, #2d1238 40%, #1a0a2a 100%)',
    borderColor: 'rgba(200,100,255,0.4)',
    titleColor: '#FF85C0',
    textColor: '#f0d4ff',
    amountColor: '#FF69B4',
    amountGlow: '0 0 40px rgba(255,105,180,0.5)',
    buttonGradient: 'linear-gradient(135deg, #b030b0 0%, #e050a0 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(200,80,200,0.4)',
    taglineColor: '#c090d0',
    particleColors: ['#FF85C0', '#DA70D6', '#DDA0DD', '#FF69B4'],
    animationType: 'milky_way',
    decoration: 'stars_heart',
    buttonText: '领取星河礼物 💕',
  },
  {
    id: 'mid_autumn',
    name: '中秋节',
    title: '中秋团圆',
    emoji: '🌕',
    poem: '但愿人长久，千里共婵娟',
    poemAuthor: '苏轼《水调歌头》',
    message: '这一轮明月，不过是宇宙中一颗普通的卫星，却因为仰望它的人而被赋予了意义。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #080a1a 0%, #0a1025 40%, #060818 100%)',
    borderColor: 'rgba(200,200,255,0.35)',
    titleColor: '#E8DCC8',
    textColor: '#d0e0f8',
    amountColor: '#E8DCC8',
    amountGlow: '0 0 40px rgba(232,220,200,0.5), 0 0 80px rgba(150,180,255,0.15)',
    buttonGradient: 'linear-gradient(135deg, #3a5a8c 0%, #5a80b0 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(100,150,255,0.3)',
    taglineColor: '#8aa0c0',
    particleColors: ['#E8DCC8', '#C0D6F5', '#B0C4DE', '#DDA0DD'],
    animationType: 'moon_rise',
    decoration: 'moon_rabbit',
    fontFamily: "'Noto Serif SC', 'STKaiti', 'KaiTi', serif",
    buttonText: '赏月领额度 🌙',
    specialEffect: 'moon_rising',
  },
  {
    id: 'double_ninth',
    name: '重阳节',
    title: '重阳登高',
    emoji: '🍂',
    poem: '遥知兄弟登高处，遍插茱萸少一人',
    poemAuthor: '王维《九月九日忆山东兄弟》',
    message: '登高望远，秋风送爽。我们来自星辰，终将回归星辰。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #1a1408 0%, #2d2512 40%, #1a160a 100%)',
    borderColor: 'rgba(218,165,32,0.35)',
    titleColor: '#DAA520',
    textColor: '#f5e6c8',
    amountColor: '#DAA520',
    amountGlow: '0 0 40px rgba(218,165,32,0.5)',
    buttonGradient: 'linear-gradient(135deg, #b8860b 0%, #daa520 100%)',
    buttonTextColor: '#1a1408',
    buttonShadow: '0 0 20px rgba(218,165,32,0.4)',
    taglineColor: '#c0a060',
    particleColors: ['#DAA520', '#CD853F', '#DEB887', '#F4A460'],
    animationType: 'climbing',
    decoration: 'chrysanthemum',
    buttonText: '登高领取',
  },
  {
    id: 'new_year',
    name: '元旦',
    title: '新年快乐',
    emoji: '🎉',
    poem: '新年都未有芳华，二月初惊见草芽',
    poemAuthor: '韩愈《春雪》',
    message: '新的一年，新的宇宙。每一个新的开始，都像是一次超新星爆发。OmicHub 送你 {amount} 额度，新年快乐！',
    gradient: 'linear-gradient(145deg, #050520 0%, #101040 40%, #080830 100%)',
    borderColor: 'rgba(100,150,255,0.5)',
    titleColor: '#ffffff',
    textColor: '#c8d8ff',
    amountColor: '#FFD700',
    amountGlow: '0 0 40px rgba(255,215,0,0.6)',
    buttonGradient: 'linear-gradient(135deg, #4a30d0 0%, #7a50ff 50%, #d040d0 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 25px rgba(100,80,255,0.5)',
    taglineColor: '#8890ff',
    particleColors: ['#FFD700', '#FF6B6B', '#4ECDC4', '#A78BFA', '#FF85C0'],
    animationType: 'new_year_fireworks',
    decoration: 'fireworks_banner',
    buttonText: '开启新宇宙 🚀',
  },
  {
    id: 'labor_day',
    name: '劳动节',
    title: '劳动节快乐',
    emoji: '🛠️',
    poem: '锄禾日当午，汗滴禾下土。谁知盘中餐，粒粒皆辛苦',
    poemAuthor: '李绅《悯农》',
    message: '劳动最光荣！每一行代码、每一次实验，都是在为这个世界创造价值。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #0a0e1a 0%, #151a28 40%, #0a1020 100%)',
    borderColor: 'rgba(255,180,50,0.35)',
    titleColor: '#FFB732',
    textColor: '#d8e4f0',
    amountColor: '#FFB732',
    amountGlow: '0 0 40px rgba(255,183,50,0.5)',
    buttonGradient: 'linear-gradient(135deg, #d08000 0%, #ffa020 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(255,160,0,0.4)',
    taglineColor: '#a0a8b8',
    particleColors: ['#FFB732', '#FFD700', '#FFA500'],
    animationType: 'gears',
    decoration: 'tools',
    buttonText: '领取',
  },
  {
    id: 'national_day',
    name: '国庆节',
    title: '国庆快乐',
    emoji: '🇨🇳',
    poem: '山河无恙，烟火寻常，这盛世如您所愿',
    poemAuthor: '——',
    message: '盛世华诞，举国同庆。送你 {amount} 额度，祝福祖国！',
    gradient: 'linear-gradient(145deg, #1a0505 0%, #2d0a0a 40%, #1a0508 100%)',
    borderColor: 'rgba(255,50,50,0.5)',
    titleColor: '#FF4444',
    textColor: '#ffd4d4',
    amountColor: '#FFD700',
    amountGlow: '0 0 40px rgba(255,215,0,0.6)',
    buttonGradient: 'linear-gradient(135deg, #cc0000 0%, #ff2222 100%)',
    buttonTextColor: '#FFD700',
    buttonShadow: '0 0 25px rgba(255,0,0,0.5)',
    taglineColor: '#d4a060',
    particleColors: ['#FF0000', '#FFD700', '#FF6B35', '#FF4444'],
    animationType: 'national_day',
    decoration: 'national_banner',
    buttonText: '庆祝 🎆',
  },
  {
    id: 'valentine',
    name: '情人节',
    title: '情人节快乐',
    emoji: '❤️',
    poem: '身无彩凤双飞翼，心有灵犀一点通',
    poemAuthor: '李商隐《无题》',
    message: '爱与被爱，都是幸福。就像两颗恒星在引力中相互环绕，永不分离。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #1a0810 0%, #2d1218 40%, #1a0a12 100%)',
    borderColor: 'rgba(255,80,120,0.4)',
    titleColor: '#FF6B9D',
    textColor: '#ffd0e0',
    amountColor: '#FF6B9D',
    amountGlow: '0 0 40px rgba(255,107,157,0.5)',
    buttonGradient: 'linear-gradient(135deg, #c44569 0%, #e86890 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(255,80,120,0.4)',
    taglineColor: '#d080a0',
    particleColors: ['#FF6B9D', '#FF85C0', '#FFB6C1', '#FF69B4'],
    animationType: 'hearts_rise',
    decoration: 'hearts',
    buttonText: '领取 💝',
  },
  {
    id: 'christmas',
    name: '圣诞节',
    title: '圣诞快乐',
    emoji: '🎄',
    poem: 'Silent night, holy night, all is calm, all is bright',
    poemAuthor: '《Silent Night》',
    message: 'Merry Christmas！愿你的代码永远无 bug，愿你的实验永远有阳性结果！送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #080a1a 0%, #0f1528 40%, #0a1020 100%)',
    borderColor: 'rgba(100,200,150,0.4)',
    titleColor: '#87CEEB',
    textColor: '#d0e8f0',
    amountColor: '#90EE90',
    amountGlow: '0 0 40px rgba(144,238,144,0.5)',
    buttonGradient: 'linear-gradient(135deg, #1a6b3a 0%, #2a9a5a 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(50,150,80,0.4)',
    taglineColor: '#80b0a0',
    particleColors: ['#ffffff', '#87CEEB', '#90EE90', '#C0E8D0'],
    animationType: 'snowfall',
    decoration: 'christmas_tree',
    buttonText: 'Ho Ho Ho 🎁',
  },
  {
    id: 'li_chun',
    name: '立春',
    title: '立春',
    emoji: '🌱',
    poem: '东风带雨逐西风，大地阳和暖气生',
    poemAuthor: '左河水',
    message: '春回大地，万物复苏。那些沉睡的种子，终将在星光的滋养下破土而出。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #081a0a 0%, #0a1e0c 40%, #061808 100%)',
    borderColor: 'rgba(100,255,150,0.35)',
    titleColor: '#90EE90',
    textColor: '#d0f5d8',
    amountColor: '#90EE90',
    amountGlow: '0 0 40px rgba(144,238,144,0.5)',
    buttonGradient: 'linear-gradient(135deg, #2a8a3a 0%, #4aaa5a 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(50,180,80,0.4)',
    taglineColor: '#70c080',
    particleColors: ['#90EE90', '#98FB98', '#FFB6C1', '#F0FFF0'],
    animationType: 'sprout',
    decoration: 'sprout',
    buttonText: '迎春 🌸',
  },
  {
    id: 'xia_zhi',
    name: '夏至',
    title: '夏至',
    emoji: '☀️',
    poem: '昼晷已云极，宵漏自此长',
    poemAuthor: '韦应物《夏至避暑北池》',
    message: '昼最长，夜最短。恒星也以最炽烈的姿态燃烧自己，照亮周遭的黑暗。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #1a1208 0%, #2d1f10 40%, #1a1608 100%)',
    borderColor: 'rgba(255,200,50,0.35)',
    titleColor: '#FFD700',
    textColor: '#f5e8c0',
    amountColor: '#FFD700',
    amountGlow: '0 0 40px rgba(255,215,0,0.5)',
    buttonGradient: 'linear-gradient(135deg, #e0a000 0%, #ffd030 100%)',
    buttonTextColor: '#1a1208',
    buttonShadow: '0 0 20px rgba(255,200,0,0.4)',
    taglineColor: '#d0b870',
    particleColors: ['#FFD700', '#FFA500', '#FF8C00', '#F0E68C'],
    animationType: 'sun_pulse',
    decoration: 'sun',
    buttonText: '领取',
  },
  {
    id: 'qiu_fen',
    name: '秋分',
    title: '秋分',
    emoji: '🍁',
    poem: '自古逢秋悲寂寥，我言秋日胜春朝',
    poemAuthor: '刘禹锡《秋词》',
    message: '昼夜均分，秋意渐浓。每一片落叶都是大自然写给我们的一封信。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #1a1008 0%, #1e140a 40%, #160e06 100%)',
    borderColor: 'rgba(210,130,50,0.35)',
    titleColor: '#D2691E',
    textColor: '#f5dcc8',
    amountColor: '#DAA520',
    amountGlow: '0 0 40px rgba(218,165,32,0.5)',
    buttonGradient: 'linear-gradient(135deg, #b8620a 0%, #d08020 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(200,120,0,0.4)',
    taglineColor: '#c09860',
    particleColors: ['#D2691E', '#CD853F', '#DEB887', '#DAA520'],
    animationType: 'maple_fall',
    decoration: 'maple',
    buttonText: '拾叶领取 🍂',
  },
  {
    id: 'dong_zhi',
    name: '冬至',
    title: '冬至',
    emoji: '❄️',
    poem: '天时人事日相催，冬至阳生春又来',
    poemAuthor: '杜甫《小至》',
    message: '冬至大如年。在最长的黑夜里，愿 OmicHub 的一点点温暖能照亮你的路。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #0a0a1a 0%, #101028 40%, #080820 100%)',
    borderColor: 'rgba(180,200,255,0.35)',
    titleColor: '#E0E8FF',
    textColor: '#c8d4f0',
    amountColor: '#B0C4DE',
    amountGlow: '0 0 40px rgba(176,196,222,0.5)',
    buttonGradient: 'linear-gradient(135deg, #3a4a7a 0%, #5a70a0 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 20px rgba(100,130,200,0.4)',
    taglineColor: '#8090b0',
    particleColors: ['#ffffff', '#C0D6F5', '#B0C4DE', '#E0E8FF'],
    animationType: 'snow_warm',
    decoration: 'snowflake',
    buttonText: '吃饺子领额度 🥟',
  },
  {
    id: 'programmers_day',
    name: '程序员节',
    title: '1024 程序员节',
    emoji: '💻',
    poem: 'Hello World!',
    poemAuthor: '每一个程序员的起点',
    message: '// 在这个特别的日子里\n// 愿你代码无bug，实验有结果\n// 愿你编译通过，论文accepted\n// OmicHub.send(amount: {amount})\n// → 领取成功 ✓',
    gradient: 'linear-gradient(145deg, #000000 0%, #0a0a0a 40%, #050505 100%)',
    borderColor: 'rgba(0,255,100,0.5)',
    titleColor: '#00FF66',
    textColor: '#00cc44',
    amountColor: '#00FF66',
    amountGlow: '0 0 40px rgba(0,255,100,0.6)',
    buttonGradient: 'linear-gradient(135deg, #000000 0%, #001a00 100%)',
    buttonTextColor: '#00FF66',
    buttonShadow: '0 0 20px rgba(0,255,100,0.4)',
    taglineColor: '#008830',
    particleColors: ['#00FF66', '#00CC44', '#00AA33'],
    animationType: 'code_rain',
    decoration: 'terminal',
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
    buttonText: 'console.log("领取")',
  },
  {
    id: 'anniversary',
    name: 'OmicHub 周年庆',
    title: 'OmicHub 一岁啦！',
    emoji: '🎂',
    poem: 'We are made of star-stuff',
    poemAuthor: 'Carl Sagan',
    message: '从第一行代码到今天，OmicHub 已经陪伴大家走过了一整年。感谢每一个深夜还在分析数据的你。送你 {amount} 额度！',
    gradient: 'linear-gradient(145deg, #0a0e27 0%, #1a1040 40%, #0e0a30 100%)',
    borderColor: 'rgba(167,139,250,0.5)',
    titleColor: '#A78BFA',
    textColor: '#d4c8ff',
    amountColor: '#A78BFA',
    amountGlow: '0 0 50px rgba(167,139,250,0.7)',
    buttonGradient: 'linear-gradient(135deg, #5b3ec0 0%, #8b5cf6 50%, #c084fc 100%)',
    buttonTextColor: '#fff',
    buttonShadow: '0 0 30px rgba(139,92,246,0.5)',
    taglineColor: '#9b8ad0',
    particleColors: ['#A78BFA', '#C084FC', '#818CF8', '#F472B6', '#FFD700'],
    animationType: 'nebula',
    decoration: 'galaxy',
    buttonText: '一起探索宇宙 🌌',
  },
]

/**
 * 根据节日名称查找主题。
 * 匹配逻辑：后端返回的节日 name 包含主题 name（例如"春节"匹配"春节"）。
 */
export function findFestivalTheme(name: string): FestivalTheme | undefined {
  return FESTIVAL_THEMES.find((t) => name.includes(t.name))
}

/**
 * 获取默认主题，兜底使用春节。
 */
export function getDefaultTheme(): FestivalTheme {
  return FESTIVAL_THEMES[0]
}

/**
 * 安全获取主题：优先按名称匹配，否则返回默认主题。
 */
export function resolveFestivalTheme(name?: string | null): FestivalTheme {
  if (!name) return getDefaultTheme()
  return findFestivalTheme(name) ?? getDefaultTheme()
}
