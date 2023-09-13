from typing import Optional, List

import enum
from pydantic import Field, BaseModel, create_model

type_for_attr = {
    'str': Optional[str],
    'int': Optional[int],
    'dict': Optional[dict],
    'list': Optional[list],
    'bool': Optional[bool]
}

default_for_attr = {
    'str': '',
    'int': 0,
    'dict': {},
    'list': [],
    'bool': False
}
ref_cls: dict = {}


class ReferenceObjectModel(BaseModel):
    id: Optional[str] = Field('', **{"description": "ID object", "access_level": "public"})
    type: Optional[str] = Field('', **{"description": "Type object", "access_level": "public"})
    name: Optional[str] = Field('', **{"description": "Name", "access_level": "public"})

    def __new__(cls, *args, **kwargs):
        return cls

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__()
        cls.object_type = kwargs.pop('object_type', '')


class ObjectModels(BaseModel):
    id: Optional[str] = Field('', **{"description": "ID object", "access_level": "public"})
    type: Optional[str] = Field('', **{"description": "Type object", "access_level": "public"})
    name: Optional[str] = Field('', **{"description": "Name", "access_level": "public"})

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__()
        cls.object_type = kwargs.pop('object_type', '')
        cls.combine = kwargs.pop('combine', None)


class BuilderMetaDataClass:

    def __init__(self, meta_name: str, type_object: str, fields: dict, params: dict, type_meta: str, combine: dict):
        self.meta_name: str = meta_name
        self.type_object: str = type_object
        self.fields: dict = fields
        self.params: dict = params
        self.type_meta: str = type_meta
        self.combine: dict = combine
        self.attrs_for_class: dict = {}
        # self.ref_cls: dict = {}
        self.ref_url: dict = {}

    async def get_ref_data(self, attr_field: Field) -> type(ReferenceObjectModel):
        global ref_cls
        ref_type = attr_field.extra['ref_type']
        if ref_cls_o := ref_cls.get(ref_type):
            return ref_cls_o
        ref_cls_o = create_model(f'Ref{ref_type}', __base__=ReferenceObjectModel)
        # ref_cls = type(f'Ref{ref_type}', (ReferenceObjectModel,), {})
        ref_cls_o.object_type = ref_type
        ref_cls[ref_type] = ref_cls_o
        if type_service := attr_field.extra.get('type_service'):
            self.ref_url[ref_type] = f'/{attr_field.extra["service_version"]}/{type_service}'
        return ref_cls_o

    async def get_type_for_attr(self, attr_field: Field) -> Optional:
        type_object_str = attr_field.extra['attrs_type']
        if type_object_str == 'ref':
            return Optional[await self.get_ref_data(attr_field)]
        elif type_object_str == 'ref_list':
            ref_cls = await self.get_ref_data(attr_field)
            return Optional[List[ref_cls]]
        elif type_object_str == 'enum':
            return Optional[attr_field.extra.pop('enum_cls')]
        else:
            return type_for_attr.get(type_object_str, str) # TODO Подумать как можно учесть тип Enum

    async def get_default_value_for_attr(self, attr_name: str) -> Optional:
        type_object_str = self.fields[attr_name]['attrs_type']
        if type_object_str == 'ref':
            return {}
        elif type_object_str == 'ref_list':
            return []
        else:
            return default_for_attr[type_object_str]

    async def get_combine(self) -> dict:
        if not self.combine:
            return {}
        class_combine_meta = type(self.meta_name, (BaseModel,), dict(**self.combine))
        return class_combine_meta().dict()

    async def set_standard_attrs(self, object_cls):
        for i, attr_field in object_cls.__fields__.items():
            if i in ('id', 'type', 'name', 'ref_metadata', 'subsystemData'):
                continue
            field_params = dict(description=attr_field.field_info.description, default=attr_field.field_info.default,
                                attrs_type=attr_field.type_.__name__,
                                show_flag=attr_field.field_info.extra.get('show_flag', True))
            if attr_field.field_info.extra.get('ref_type'):
                field_params['attrs_type'] = 'ref_list' if field_params['attrs_type'] == 'list' \
                                                           or isinstance(field_params['default'], list) else 'ref'
                field_params.update(attr_field.field_info.extra)
            elif isinstance(attr_field.outer_type_, enum.EnumMeta):
                field_params['attrs_type'] = 'enum'
                field_params['enum_cls'] = attr_field.outer_type_
            field_cls = Field(**field_params)
            self.attrs_for_class.update({i: (await self.get_type_for_attr(field_cls), field_cls)})

    async def build_metadata_object(self, object_cls: type(ObjectModels)) -> type(ObjectModels):
        await self.set_standard_attrs(object_cls)
        for attr_name, field in self.fields.items():
            await self.build_attrs_field(attr_name, field)
        return await self.build_class_for_meta()

    async def build_attrs_field(self, attr_name, attr_params):
        if not attr_params['show_flag'] and attr_name in self.attrs_for_class:
            del self.attrs_for_class[attr_name]
        field_params = dict(description=attr_params['description'], attrs_type=attr_params['attrs_type'],
                            default=await self.get_default_value_for_attr(attr_name))
        if attr_name.startswith('ref_') or attr_params['type_object']:
            field_params.update(dict(ref_type=attr_params['type_object'], attrs=attr_params['attrs'],
                                     links=attr_params['links'],
                                     type_service=attr_params['type_service'],
                                     service_version=attr_params['service_version']))
        field_cls = Field(**field_params)
        self.attrs_for_class.update({attr_name: (await self.get_type_for_attr(field_cls), field_cls)})

    async def build_class_for_meta(self) -> type(ObjectModels):
        class_for_meta = create_model(self.meta_name, **dict(**self.attrs_for_class), __base__=ObjectModels)
        class_for_meta.object_type = self.meta_name
        return class_for_meta
