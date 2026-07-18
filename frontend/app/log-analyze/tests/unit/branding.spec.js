import { PRODUCT_NAME, PRODUCT_SUBTITLE } from '@/config/branding'

describe('fault analysis branding', () => {
  test('uses the fault analysis product name and scope', () => {
    expect(PRODUCT_NAME).toBe('故障分析工具')
    expect(PRODUCT_SUBTITLE).toContain('日志')
    expect(PRODUCT_SUBTITLE).toContain('图片')
    expect(PRODUCT_SUBTITLE).toContain('代码')
  })
})
