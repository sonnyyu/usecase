import csv
import inspect
from io import BytesIO
import logging
import six
import sys
import warnings

from markupsafe import Markup
from werkzeug import secure_filename
from wtforms.fields import HiddenField
from wtforms.fields import IntegerField
from wtforms.fields import PasswordField
from wtforms.fields import StringField
from wtforms.form import BaseForm
from wtforms.validators import InputRequired

from sqlalchemy import func

import flask
from flask import make_response
from flask import request
from flask_login import current_user

from flask_admin.base import AdminIndexView
from flask_admin.base import expose
from flask_admin.base import MenuLink
from flask_admin.contrib.sqla.fields import QuerySelectField
from flask_admin.contrib.sqla.form import AdminModelConverter
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import FileUploadField
from flask_admin.form import SecureForm
from flask_admin.helpers import get_form_data
from flask_admin.helpers import get_redirect_target
from flask_admin.model.fields import AjaxSelectField
from flask_admin.model.template import EndpointLinkRowAction

from usecase.db import database
from usecase.db import models


logger = logging.getLogger(__name__)
MODELS = {
    clazz.__tablename__: clazz
    for clazz in models.BASE._decl_class_registry.values()
    if isinstance(clazz, type) and issubclass(clazz, models.BASE)
}
if sys.version_info > (3,):
    long = int
    basestring = str
    integer_types = (int,)
    string_types = (str, bytes)
else:
    integer_types = (int, long)
    string_types = (basestring,)


class ForeignKeyModelConverter(AdminModelConverter):
    def get_converter(self, column):
        for foreign_key in column.foreign_keys:
            return self.convert_foreign_key
        return super(ForeignKeyModelConverter, self).get_converter(column)

    def convert_foreign_key(self, column, field_args, **extra):
        loader = getattr(self.view, '_form_ajax_refs', {}).get(column.name)
        if loader:
            return AjaxSelectField(loader, **field_args)
        if 'query_factory' not in field_args:
            remote_model = None
            remote_column = None
            for foreign_key in column.foreign_keys:
                remote_column = foreign_key.column
                remote_model = MODELS[remote_column.table.fullname]
            field_args['query_factory'] = (
                lambda: [
                    getattr(obj, remote_column.name)
                    for obj in self.session.query(remote_model).all()
                ]
            )
            field_args['get_pk'] = lambda obj: obj
            field_args['get_label'] = lambda obj: obj
        return QuerySelectField(**field_args)


class BaseModelView(ModelView):
    form_base_class = SecureForm
    column_display_pk = True
    can_export = True
    can_view_details = True
    can_update = False
    can_delete_with = False
    can_import = False
    can_statistics = False
    model_form_converter = ForeignKeyModelConverter
    import_types = ['csv']
    import_primary_fields = []
    import_override_fields = {}
    import_exclude_fields = []
    update_columns = []
    statistics_columns = []
    upload_template = 'admin/model/upload.html'
    update_template = 'admin/model/update.html'
    statistics_template = 'admin/model/statistics.html'

    def __init__(self, model, session, *args, **kwargs):
        # self.column_labels = {
        #     name: column.name
        #     for name, column in six.iteritems(dict(model.__table__.columns))
        # }
        # logger.debug('model %s columns: %s', model, self.column_list)
        # logger.debug('model %s column labels: %s', model, self.column_labels)
        # self.form_columns = model.__table__.columns.keys()
        # self.column_export_list = model.__table__.columns.keys()
        self.session = session
        super(BaseModelView, self).__init__(model, session, *args, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        # redirect to login page if user doesn't have access
        return flask.redirect(flask.url_for('login', next=request.url))

    def update_form(self, update_args):
        active_columns = update_args.values()
        logger.error('active columns: %s', active_columns)
        logger.error('update columns: %s', self._update_columns)
        update_fields = {}
        field_mapping = {
            column.name: column.type.python_type
            for column in self.model.__table__.columns
        }
        for column_name in self._update_columns:
            if column_name in active_columns:
                field_type = field_mapping[column_name]
                logger.error('column %s type %s', column_name, field_type)
                if issubclass(field_type, string_types):
                    update_fields[column_name] = StringField()
                elif issubclass(field_type, integer_types):
                    update_fields[column_name] = IntegerField()
        logger.error('update fields: %s', update_fields)
        form = BaseForm(update_fields)
        form.process(get_form_data(), obj=None)
        return form

    @expose('/delete_with/', methods=('GET', 'POST'))
    def delete_with_view(self):
        return_url = get_redirect_target() or self.get_url('.index_view')
        if not self.can_delete_with:
            return flask.redirect(return_url)
        # Grab parameters from URL
        view_args = self._get_list_extra_args()
        filter_args = self._get_filters(view_args.filters)
        logger.error(
            'delete request method %s filter args: %s',
            request.method, filter_args
        )
        try:
            self.delete_models(view_args.filters)
        except Exception as ex:
            flask.flash(str(ex), 'error')
            logger.exception(ex)
        return flask.redirect(
            return_url
        )

    def get_update_columns(self):
        if self.update_columns:
            return self.update_columns
        else:
            return [
                column.name for column in self.model.__table__.columns
            ]

    def get_statistics_columns(self):
        if self.statistics_columns:
            return self.statistics_columns
        else:
            return [
                column.name for column in self.model.__table__.columns
            ]

    def _get_update_args(self):
        if self._update_columns:
            updates = {}

            for n in request.args:
                if not n.startswith('upt'):
                    continue
                if '_' not in n:
                    continue
                updates[n] = request.args[n]
            return updates
        return None

    @expose('/update/', methods=('GET', 'POST'))
    def update_view(self):
        return_url = get_redirect_target() or self.get_url('.index_view')
        if not self.can_update:
            return flask.redirect(return_url)
        # Grab parameters from URL
        view_args = self._get_list_extra_args()
        filter_args = self._get_filters(view_args.filters)
        update_args = self._get_update_args()
        logger.error(
            'update request method %s filter args: %s, update args: %s',
            request.method, filter_args, update_args
        )
        form = self.update_form(update_args)
        if self.validate_form(form):
            try:
                self.update_models(form, view_args.filters)
            except Exception as ex:
                flask.flash(str(ex), 'error')
                logger.exception(ex)
            return flask.redirect(
                return_url
            )
        template = self.update_template
        return self.render(
            template,
            form=form,
            # Filters
            filters=self._filters,
            filter_groups=self._get_filter_groups(),
            active_filters=view_args.filters,
            filter_args=filter_args,
            update_columns=self._update_columns,
            update_args=update_args,
            return_url=return_url
        )

    def get_upload_form(self):
        class UploadForm(self.form_base_class):
            upload = FileUploadField(validators=[InputRequired()])
            url = HiddenField()

        return UploadForm

    def upload_form(self, obj=None):
        return self._upload_form_class(get_form_data(), obj=obj)

    def _refresh_forms_cache(self):
        super(BaseModelView, self)._refresh_forms_cache()
        self._upload_form_class = self.get_upload_form()
        self._update_columns = self.get_update_columns()
        self._statistics_columns = self.get_statistics_columns()

    def delete_models(self, filters):
        query = self.get_query()
        for idx, flt_name, value in filters:
            alias = None
            flt = self._filters[idx]
            clean_value = flt.clean(value)
            try:
                query = flt.apply(query, clean_value, alias)
            except TypeError:
                spec = inspect.getargspec(flt.apply)
                if len(spec.args) == 3:
                    warnings.warn(
                        'Please update your custom filter %s to '
                        'include additional `alias` parameter.' % repr(flt)
                    )
                else:
                    raise
                query = flt.apply(query, clean_value)
        logger.error('query is %s', query)
        query.delete(synchronize_session='fetch')

    def update_models(self, form, filters):
        query = self.get_query()
        for idx, flt_name, value in filters:
            alias = None
            flt = self._filters[idx]
            clean_value = flt.clean(value)
            try:
                query = flt.apply(query, clean_value, alias)
            except TypeError:
                spec = inspect.getargspec(flt.apply)
                if len(spec.args) == 3:
                    warnings.warn(
                        'Please update your custom filter %s to '
                        'include additional `alias` parameter.' % repr(flt)
                    )
                else:
                    raise
                query = flt.apply(query, clean_value)
        logger.error('query is %s', query)
        data = form.data
        logger.error('update fields to %s', data)
        query.update(data, synchronize_session='fetch')

    def statistics_models(self, filters, aggregation):
        column = getattr(self.model, aggregation)
        query = self.session.query(
            column, func.count('*').label('count')
        ).group_by(aggregation)
        for idx, flt_name, value in filters:
            alias = None
            flt = self._filters[idx]
            clean_value = flt.clean(value)
            try:
                query = flt.apply(query, clean_value, alias)
            except TypeError:
                spec = inspect.getargspec(flt.apply)
                if len(spec.args) == 3:
                    warnings.warn(
                        'Please update your custom filter %s to '
                        'include additional `alias` parameter.' % repr(flt)
                    )
                else:
                    raise
                query = flt.apply(query, clean_value)
        logger.error('query is %s', query)
        return query.all()

    def upload_model(self, file_storage):
        field_mapping = {
            column.name: column.type.python_type
            for column in self.model.__table__.columns
        }
        converted_data = {}
        for key, value in six.iteritems(self.import_override_fields):
            if key not in field_mapping:
                raise Exception(
                    'key %s not in model fields %s' % (
                        key, field_mapping.keys()
                    )
                )
            if value is not None:
                converted_data[key] = models.convert_column_value(
                    value, field_mapping[key]
                )
            else:
                converted_data[key] = value
        if self.import_primary_fields:
            primary_fields = self.import_primary_fields
        else:
            primary_fields = [
                column.name
                for column in self.model.__table__.primary_key
            ]
        fields = None
        reader = csv.reader(file_storage)
        data = []
        for row in reader:
            if not row:
                continue
            row = [
                item.strip()
                for item in row
            ]
            logger.debug('read row: %s', row)
            if not fields:
                fields = row
                for field in fields:
                    if (field not in field_mapping):
                        raise Exception(
                            "unknown field %r which should be in %r" % (
                                field, field_mapping.keys()
                            )
                        )
                if primary_fields:
                    missing_primary = []
                    for key in primary_fields:
                        if key not in fields:
                            missing_primary.append(key)
                    if missing_primary:
                        raise Exception(
                            'missing primary key: %s in fields %s',
                            missing_primary, fields
                        )
            else:
                row = dict(zip(fields, row))
                row_data = {}
                if primary_fields:
                    missing_primary = []
                    for key in primary_fields:
                        if key not in row:
                            missing_primary.append(key)
                    if missing_primary:
                        raise Exception(
                            'missing primary key: %s in row',
                            missing_primary, row
                        )
                for key, value in six.iteritems(row):
                    if value:
                        row_data[key] = models.convert_column_value(
                            value, field_mapping[key]
                        )
                row_data.update(converted_data)
                data.append(row_data)
        try:
            for row_data in data:
                if primary_fields:
                    primary_data = {}
                    for key in primary_fields:
                        primary_data[key] = row_data[key]
                    result = self.session.query(
                        self.model
                    ).filter_by(**primary_data).first()
                    if result:
                        for key, value in six.iteritems(row_data):
                            if key not in primary_data:
                                setattr(result, key, value)
                    else:
                        result = self.model(**row_data)
                        self.session.add(result)
                else:
                    result = self.model(**row_data)
                    self.session.add(result)
            self.session.commit()
        except Exception as ex:
            logger.exception(ex)
            self.session.rollback()
            raise ex
        return True

    def download_model(self, filters):
        field_mapping = {
            column.name: column.type.python_type
            for column in self.model.__table__.columns
        }
        primary_fields = [
            column.name
            for column in self.model.__table__.primary_key
        ]
        column_names = []
        rows = {}
        output = []
        column_names.extend(primary_fields)
        for column_name in field_mapping:
            if column_name not in primary_fields:
                column_names.append(column_name)
        query = self.get_query()
        for idx, flt_name, value in filters:
            alias = None
            flt = self._filters[idx]
            clean_value = flt.clean(value)
            try:
                query = flt.apply(query, clean_value, alias)
            except TypeError:
                spec = inspect.getargspec(flt.apply)
                if len(spec.args) == 3:
                    warnings.warn(
                        'Please update your custom filter %s to '
                        'include additional `alias` parameter.' % repr(flt)
                    )
                else:
                    raise
                query = flt.apply(query, clean_value)
        logger.error('query is %s', query)
        result = query.all()
        for item in result:
            item_dict = item.to_dict()
            item_keys = []
            for primary_key in primary_fields:
                item_keys.append(item_dict[primary_key])
            rows[tuple(item_keys)] = item_dict
        exported_keys = sorted(rows.keys())
        output.append(column_names)
        for exported_key in exported_keys:
            row = rows[exported_key]
            item = []
            for column_name in column_names:
                value = row.get(column_name, "") or ""
                value = models.reverse_convert_column_value(
                    value, field_mapping[column_name]
                )
                item.append(value)
            output.append(item)
        string_buffer = BytesIO()
        writer = csv.writer(string_buffer)
        writer.writerows(output)
        return string_buffer.getvalue()

    @expose('/export/<export_type>/')
    def export(self, export_type):
        return_url = get_redirect_target() or self.get_url('.index_view')

        if not self.can_export:
            return flask.redirect(return_url)
        # Grab parameters from URL
        view_args = self._get_list_extra_args()
        filter_args = self._get_filters(view_args.filters)
        logger.error(
            'update request method %s filter args: %s',
            request.method, filter_args
        )

        try:
            content = self.download_model(view_args.filters)
        except Exception as ex:
            flask.flash(str(ex), 'error')
            logger.exception(ex)
            return flask.redirect(
                return_url
            )
        resp = make_response(content, 200)
        resp.mimetype = 'text/csv'
        filename = self.get_export_name(export_type='csv')
        resp.headers['Content-Disposition'] = 'attachment; filename="%s"' % (
            secure_filename(filename),
        )
        return resp

    @expose('/import/<import_type>', methods=('GET', 'POST'))
    def import_view(self, import_type):
        return_url = get_redirect_target() or self.get_url('.index_view')
        if not self.can_import:
            return flask.redirect(return_url)
        form = self.upload_form()
        if self.validate_form(form):
            file_storage = form.upload.data
            try:
                self.upload_model(file_storage)
            except Exception as ex:
                flask.flash(str(ex), 'error')
                logger.exception(ex)
            return flask.redirect(
                return_url
            )
        template = self.upload_template
        return self.render(
            template,
            form=form,
            return_url=return_url
        )

    @expose('/statistics/', methods=('GET', 'POST'))
    def statistics_view(self):
        return_url = get_redirect_target() or self.get_url('.index_view')
        if not self.can_statistics:
            return flask.redirect(return_url)
        # Grab parameters from URL
        view_args = self._get_list_extra_args()
        aggregation = request.args['aggregation']
        filter_args = self._get_filters(view_args.filters)
        logger.error(
            'update request method %s filter args: %s, '
            'aggregation: %s',
            request.method, filter_args, aggregation
        )
        try:
            data = self.statistics_models(
                view_args.filters, aggregation
            )
        except Exception as ex:
            flask.flash(str(ex), 'error')
            logger.exception(ex)
            return flask.redirect(
                return_url
            )
        logger.error('statistics data: %s', data)
        template = self.statistics_template
        return self.render(
            template,
            aggregation_key=aggregation,
            aggregation_labels=[
                item[0] or 'Null' for item in data
            ],
            aggregation_values=[item[1] for item in data],
            return_url=return_url
        )


def link_dashboard_formatter(view, context, model, name):
    dashboard = getattr(model, 'dashboard')
    name = getattr(model, 'name')
    return Markup(
        '<a href="{}" target="_blank">{}</a>'.format(dashboard, name)
    )


class ShowCaseModelView(BaseModelView):
    column_searchable_list = ['app', 'name', 'category']
    column_filters = [
        'app', 'name', 'category', 'domain',
        'owner', 'developer'
    ]
    column_list = [
        'name', 'category', 'dashboard', 'domain',
        'owner', 'developer'
    ]
    column_formatters = {
        'dashboard': link_dashboard_formatter
    }
    column_formatters_detail = {
        'dashboard': link_dashboard_formatter
    }
    column_details_list = [
        'name', 'category', 'dashboard', 'domain',
        'owner', 'developer', 'description',
        'help'
    ]
    can_import = True
    can_statistics = True
    import_primary_fields = ['name']


class ShowCaseDemoModelView(BaseModelView):
    column_searchable_list = ['examples_name', 'label']
    column_filters = ['examples_name', 'label']
    column_list = ['id', 'examples_name', 'label', 'value']
    can_import = True
    can_update = True
    can_delete = True
    import_primary_fields = ['examples_name']


class UserModelView(BaseModelView):
    column_searchable_list = ['email']
    column_list = ['id', 'email', 'password']
    column_details_list = [
        'id', 'email', 'password', 'firstname', 'lastname',
        'is_admin', 'active'
    ]
    # form_columns = [
    #     'email', 'password', 'firstname', 'lastname',
    #     'is_admin', 'active'
    # ]
    form_excluded_columns = ['crypted_password', 'user_tokens']
    form_extra_fields = {'name': PasswordField('password')}
    column_extra_row_actions = [
        EndpointLinkRowAction(
            'off glyphicon glyphicon-off',
            'user.activate_user_view',
        )
    ]

    @expose('/activate/', methods=('GET',))
    def activate_user_view(self):
        id = request.args["id"]
        model = self.get_one(id)
        return_url = get_redirect_target() or self.get_url('.index_view')
        if model is None:
            flask.flash('use does not exist', 'error')
            return flask.redirect(return_url)

        if model.active:
            flask.flash('user is already active', 'warning')
            return flask.redirect(return_url)

        model.active = True
        model.save()

        flask.flash('use is active now', 'success')
        return flask.redirect(return_url)


class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            logger.error('current user %s is not authenticated', current_user)
            next_url = request.url
            return flask.redirect(flask.url_for('login', next=next_url))
        # import pdb;pdb.set_trace()
        if current_user.is_admin:
            logger.info('current user %s is admin', current_user)
            return super(MyAdminIndexView, self).index()
        else:
            logger.info('current user %s is not admin', current_user)
            return flask.redirect(flask.url_for("index"))


ModelViewMapping = {
    'showcasecn': ShowCaseModelView,
    'showcaseen': ShowCaseModelView,
    'showcasedemo': ShowCaseDemoModelView,
    'user': UserModelView
}


def init():
    from usecase.api import admin
    models = sorted(MODELS.keys())
    for model_name in models:
        if model_name in ModelViewMapping:
            model = MODELS[model_name]
            logger.debug('add model %s view %s', model_name, model)
            print("add model %s view %s", model_name, model)
            admin.add_view(
                ModelViewMapping[model_name](
                    model, database.SCOPED_SESSION
                )
            )
    admin.add_link(MenuLink(name='Logout', endpoint='logout'))
