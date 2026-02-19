import os
import asyncio
from backend.utils.database import DatabaseManager
from backend.utils.config import Config
from backend.modules.pipeline_runner import PipelineRunner
from pathlib import Path

async def run_pipeline():
    db = DatabaseManager(os.getenv('DATABASE_URL'))
    config = Config()
    
    # Check if a pipeline is already running
    if db.has_active_pipeline_run():
        print("Pipeline is already running.")
        return

    # Create run
    steps_template = PipelineRunner.build_steps_template()
    run_id = db.create_pipeline_run(steps_template)
    print(f"Created run {run_id}")

    # Use scraping=False to process local files
    options = {
        "use_scraping": False,
        "use_pagination": False,
        "year": 2023,
        "month": 7
    }
    
    runner = PipelineRunner(config, db, run_id, options=options)
    runner.run() # Synchronous run
    print("Pipeline finished.")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
