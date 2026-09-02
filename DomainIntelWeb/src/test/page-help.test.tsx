import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import PageHelp from '../features/PageHelp'

afterEach(cleanup)

it('shows page-specific user guidance from the persistent help badge',()=>{
  const {rerender}=render(<PageHelp page="daily"/>)
  fireEvent.click(screen.getByRole('button',{name:'打开本页使用指南'}))
  expect(screen.getByRole('dialog',{name:'每日情报使用指南'})).toBeInTheDocument()
  expect(screen.getByText(/前一日凌晨 04:00/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'关闭使用指南'}))
  rerender(<PageHelp page="sources"/>)
  fireEvent.click(screen.getByRole('button',{name:'打开本页使用指南'}))
  expect(screen.getByRole('dialog',{name:'信息源使用指南'})).toBeInTheDocument()
  expect(screen.getByText(/来源目录/)).toBeInTheDocument()
})
