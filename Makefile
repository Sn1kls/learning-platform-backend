.PHONY: build upd migrate migrations superuser collectstatic tests

build:
	docker-compose -f docker-compose.dev.yaml build

upd:
	docker-compose -f docker-compose.dev.yaml up -d

migrate:
	docker-compose -f docker-compose.dev.yaml exec web python manage.py migrate

migrations:
	docker-compose -f docker-compose.dev.yaml exec web python manage.py makemigrations

superuser:
	docker-compose -f docker-compose.dev.yaml exec web python manage.py createsuperuser

tests:
	docker-compose -f docker-compose.dev.yaml exec web python manage.py test

collectstatic:
	docker-compose -f docker-compose.dev.yaml exec web python manage.py collectstatic --noinput