Ручное отключение Node на странице Nodes в админке "Disable"


Маленькая, но важная правка по датам (рекомендую)
В моделях:
created_at: default=datetime.now()
Это вычисляется в момент импорта модуля (плохой баг). Нужно без скобок:
created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
То же самое в ComfyNode, Job, JobExecution.
