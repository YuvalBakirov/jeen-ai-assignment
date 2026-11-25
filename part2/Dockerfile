FROM langflowai/langflow:1.13.3
COPY --chown=user:user patches/restore_resume_dependencies.py /tmp/restore_resume_dependencies.py
RUN python /tmp/restore_resume_dependencies.py && rm /tmp/restore_resume_dependencies.py
