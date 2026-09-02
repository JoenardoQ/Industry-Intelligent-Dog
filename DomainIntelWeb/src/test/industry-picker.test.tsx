import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import IndustryPicker from '../features/IndustryPicker'

afterEach(cleanup)

it('uses an accessible consistent listbox and supports keyboard selection',()=>{
  const change=vi.fn()
  render(<IndustryPicker industries={[{folder:'ai',name:'人工智能'},{folder:'chips',name:'芯片'}] as never} value="ai" onChange={change}/>)
  const picker=screen.getByRole('combobox',{name:'当前行业'})
  fireEvent.keyDown(picker,{key:'ArrowDown'})
  expect(screen.getByRole('listbox')).toBeInTheDocument()
  fireEvent.keyDown(picker,{key:'ArrowDown'})
  fireEvent.keyDown(picker,{key:'Enter'})
  expect(change).toHaveBeenCalledWith('chips')
})
