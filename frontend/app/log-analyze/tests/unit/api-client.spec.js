import apiClient from '@/api/client'
import moduleApi from '@/api/module'
import productApi from '@/api/product'


jest.mock('@/api/client', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn()
  }
}))


describe('shared API client contracts', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.post.mockReset()
  })

  test('product requests use the shared client', async () => {
    apiClient.get.mockResolvedValue({ data: { products: [] } })

    await productApi.getProducts()

    expect(apiClient.get).toHaveBeenCalledWith('/product/get')
  })

  test('module requests use the shared client', async () => {
    apiClient.get.mockResolvedValue({ data: { modules: [] } })

    await moduleApi.getModulesByProduct(7)

    expect(apiClient.get).toHaveBeenCalledWith('/module/get', { params: { product_id: 7 } })
  })
})
