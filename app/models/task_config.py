class TaskConfig:
    def __init__(self, job_type, queue="background"):
        self.source = f"_{job_type}_knowledge"
        self.job_type = job_type
        self.job_prefix = f"{job_type}_embedding"
        self.pending_task_name = f"{job_type}_embedding.get_pending_jobs"
        self.task_name = f"{job_type}_embedding.task_processing"
        self.queue_name = queue