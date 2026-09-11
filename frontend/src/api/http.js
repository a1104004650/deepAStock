import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 60000
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    if (Array.isArray(msg)) {
      ElMessage.error(msg.map((m) => m.msg).join('; '))
    } else {
      ElMessage.error(String(msg))
    }
    return Promise.reject(err)
  }
)

export default http