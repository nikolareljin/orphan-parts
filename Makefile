# Thin aliases; ./dev is the real entry point.
.PHONY: help setup up down status test lint fmt docs build

help:
	@./dev help

setup:
	@./dev setup

up:
	@./dev up

down:
	@./dev down

status:
	@./dev status

test:
	@./dev test

lint:
	@./dev lint

fmt:
	@./dev fmt

docs:
	@./dev docs

build:
	@./dev build
