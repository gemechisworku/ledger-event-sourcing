import '@xyflow/react/dist/style.css'

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  Handle,
  Position,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { memo, useCallback, useEffect, useMemo, type MouseEvent } from 'react'

import { deriveStageStatuses } from '@/lib/derive-stage-status'
import { PIPELINE_STAGES } from '@/lib/pipeline-stages'
import { cn } from '@/lib/utils'
import type { PipelineSseEvent } from '@/types/pipeline-sse'
import type { StageStatus } from '@/types/pipeline-sse'

const NODE_W = 140
const GAP = 48

type StageData = { label: string; status: StageStatus; selected: boolean }

function StageNode({ data }: NodeProps) {
  const { label, status, selected } = data as StageData
  return (
    <div
      className={cn(
        'min-w-[132px] rounded-2xl border border-border/70 bg-gradient-to-b from-card to-muted/40 px-3 py-2.5 text-center text-sm font-semibold capitalize shadow-md ring-1 ring-border/40 backdrop-blur-sm transition-all duration-200',
        selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
        status === 'running' &&
          'border-primary/80 bg-gradient-to-b from-primary/15 to-primary/5 shadow-[0_0_24px_hsl(var(--primary)/0.25)]',
        status === 'completed' &&
          'border-emerald-500/40 bg-gradient-to-b from-emerald-500/15 to-emerald-600/5 shadow-sm',
        status === 'failed' && 'border-destructive/60 bg-destructive/10',
        status === 'idle' && 'border-border/50 opacity-90',
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border-2 !border-background !bg-primary"
      />
      <span className="text-foreground">{label}</span>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !border-2 !border-background !bg-primary"
      />
    </div>
  )
}

const nodeTypes = { stage: memo(StageNode) }

function buildNodesEdges(
  statuses: Record<string, StageStatus>,
  selectedStage: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = PIPELINE_STAGES.map((s, i) => ({
    id: s,
    type: 'stage',
    position: { x: i * (NODE_W + GAP), y: 24 },
    data: {
      label: s,
      status: statuses[s] ?? 'idle',
      selected: selectedStage === s,
    } satisfies StageData,
  }))
  const edges: Edge[] = []
  for (let i = 0; i < PIPELINE_STAGES.length - 1; i++) {
    const a = PIPELINE_STAGES[i]
    const b = PIPELINE_STAGES[i + 1]
    edges.push({
      id: `${a}-${b}`,
      source: a,
      target: b,
      animated: statuses[a] === 'running',
      style: {
        stroke: 'hsl(var(--primary) / 0.45)',
        strokeWidth: 2,
      },
    })
  }
  return { nodes, edges }
}

type Props = {
  sseEvents: PipelineSseEvent[]
  selectedStage: string | null
  onSelectStage: (id: string) => void
}

function PipelineGraphInner({ sseEvents, selectedStage, onSelectStage }: Props) {
  const statuses = useMemo(() => deriveStageStatuses(sseEvents), [sseEvents])
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  useEffect(() => {
    const { nodes: n, edges: e } = buildNodesEdges(statuses, selectedStage)
    setNodes(n)
    setEdges(e)
  }, [statuses, selectedStage, setNodes, setEdges])

  const onNodeClick = useCallback(
    (_: MouseEvent, n: Node) => {
      onSelectStage(n.id)
    },
    [onSelectStage],
  )

  return (
    <div className="h-[300px] w-full overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-muted/40 via-background to-primary/5 shadow-inner ring-1 ring-border/40">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        onNodeClick={onNodeClick}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          style: { stroke: 'hsl(var(--primary) / 0.4)', strokeWidth: 2 },
        }}
      >
        <Background gap={20} size={1} className="opacity-40" />
        <MiniMap zoomable pannable className="!rounded-lg !border !border-border/60 !bg-card/95 !shadow-md" />
        <Controls className="!rounded-lg !border !border-border/60 !bg-card/95 !shadow-md" />
      </ReactFlow>
    </div>
  )
}

export function PipelineGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <PipelineGraphInner {...props} />
    </ReactFlowProvider>
  )
}
