FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/aws_etl_news/ ${LAMBDA_TASK_ROOT}/aws_etl_news/

CMD ["aws_etl_news.lambda_handler.handler"]