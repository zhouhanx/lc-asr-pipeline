export function TaskModelName({
  name,
  deleted,
}: {
  name: string
  deleted: boolean
}) {
  return (
    <span>
      <strong className={deleted ? 'line-through decoration-2 decoration-destructive' : ''}>{name}</strong>
      {deleted && <span className="ml-2 font-sans text-xs font-bold text-destructive">模型当前已删除</span>}
    </span>
  )
}
